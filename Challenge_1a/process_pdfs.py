import fitz
import os
import json
import re
import sys
from collections import defaultdict, namedtuple
from typing import List, Tuple, Dict, Optional

TextBlock = namedtuple('TextBlock', ['text', 'size', 'font', 'bold', 'x0', 'y0', 'x1', 'y1', 'page_num'])

class PDFOutlineExtractor:
    def __init__(self):
        self.body_font_size = 0
        self.font_thresholds = {
            'H1': 1.4,
            'H2': 1.2,
            'H3': 1.05
        }
        self.min_block_length = 3

    def process_pdf(self, pdf_path: str) -> Dict:
        doc = fitz.open(pdf_path)
        self._analyze_body_font(doc)
        all_blocks = self._extract_all_blocks(doc)
        headings = self._extract_headings(all_blocks)
        title = self._extract_title(doc, all_blocks)
        return {
            "title": title,
            "outline": [
                {"level": h["level"], "text": h["text"], "page": h["page"]}
                for h in headings
            ]
        }

    def _analyze_body_font(self, doc: fitz.Document):
        font_counts = defaultdict(int)
        for page_num in range(min(3, len(doc))):
            blocks = self._extract_text_blocks(doc[page_num])
            for b in blocks:
                if len(b.text) > 5 and not b.bold:
                    font_counts[round(b.size, 1)] += 1
        self.body_font_size = max(font_counts.items(), key=lambda x: x[1])[0] if font_counts else 10.0

    def _extract_all_blocks(self, doc: fitz.Document) -> List[TextBlock]:
        all_blocks = []
        for page in doc:
            all_blocks.extend(self._extract_text_blocks(page))
        return all_blocks

    def _extract_text_blocks(self, page: fitz.Page) -> List[TextBlock]:
        blocks = []
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                line_text = ""
                span_props = None
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text or len(text) < 2:
                        continue
                    if span_props is None:
                        span_props = span
                    line_text += text + " "
                if line_text and span_props:
                    blocks.append(TextBlock(
                        text=line_text.strip(),
                        size=span_props["size"],
                        font=span_props["font"],
                        bold=bool(span_props["flags"] & 16),
                        x0=span_props["bbox"][0],
                        y0=span_props["bbox"][1],
                        x1=span_props["bbox"][2],
                        y1=span_props["bbox"][3],
                        page_num=page.number + 1
                    ))
        return blocks

    def _extract_headings(self, blocks: List[TextBlock]) -> List[Dict]:
        headings = []
        for block in blocks:
            if self._is_heading(block):
                level = self._get_level(block)
                if level:
                    headings.append({
                        "level": level,
                        "text": block.text.strip(),
                        "page": block.page_num,
                        "y0": block.y0
                    })
        seen = set()
        final = []
        for h in sorted(headings, key=lambda x: (x["page"], x["y0"])):
            key = (h["text"].lower(), h["page"])
            if key in seen:
                continue
            seen.add(key)
            final.append(h)
        return final

    def _is_heading(self, block: TextBlock) -> bool:
        text = block.text.strip()
        if len(text) < self.min_block_length:
            return False
        if block.bold or block.size >= self.body_font_size * 1.05:
            return True
        if re.match(r'^\d+(\.\d+)*\s', text):
            return True
        if any(ord(c) > 255 for c in text):
            return True
        return False

    def _get_level(self, block: TextBlock) -> Optional[str]:
        text = block.text.strip()
        if re.match(r'^\d+\.\d+\.\d+\s+', text):
            return "H3"
        if re.match(r'^\d+\.\d+\s+', text):
            return "H2"
        if re.match(r'^\d+\s+', text):
            return "H1"
        size_ratio = block.size / self.body_font_size if self.body_font_size else 1.0
        if size_ratio >= self.font_thresholds['H1']:
            return "H1"
        if size_ratio >= self.font_thresholds['H2']:
            return "H2"
        if size_ratio >= self.font_thresholds['H3'] or block.bold:
            return "H3"
        return None

    def _extract_title(self, doc: fitz.Document, blocks: List[TextBlock]) -> str:
        page1_blocks = [b for b in blocks if b.page_num == 1]
        if not page1_blocks:
            return "Document Title"
        sorted_blocks = sorted(page1_blocks, key=lambda b: (-b.size, b.y0))
        top_size = sorted_blocks[0].size
        page_width = doc[0].rect.width
        for b in sorted_blocks:
            if b.y0 > 300:
                continue
            if abs(b.size - top_size) > 2.0:
                continue
            if re.match(r"^\d+[\).]?\s+", b.text.strip()):
                continue
            if b.text.strip().lower() in {"overview", "table of contents", "revision history"}:
                continue
            center_x = (b.x0 + b.x1) / 2
            if abs(center_x - page_width / 2) > page_width * 0.25:
                continue
            title = b.text.strip()
            title = re.sub(r'\b(\w+)( \1\b)+', r'\1', title)
            title = re.sub(r'\s{2,}', ' ', title)
            return title if len(title) > 5 else "Document Title"
        return "Document Title"

def save_json(data: Dict, output_path: str):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def process_all_pdfs(input_dir: str, output_dir: str):
    extractor = PDFOutlineExtractor()
    for filename in os.listdir(input_dir):
        if filename.lower().endswith(".pdf"):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename.replace(".pdf", ".json"))
            try:
                result = extractor.process_pdf(input_path)
                save_json(result, output_path)
                print(f"Processed: {filename}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    input_dir = "sample_dataset/pdfs"
    output_dir = "sample_dataset/outputs"
    os.makedirs(output_dir, exist_ok=True)
    process_all_pdfs(input_dir, output_dir) 
