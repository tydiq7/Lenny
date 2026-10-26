"""Turn an uploaded image or PDF into PIL images that Gemma can read."""
import io

from PIL import Image

MAX_PAGES_PER_FILE = 6


def file_to_images(uploaded, notes):
    """Return a list of PIL images for a Streamlit upload: one for a photo, one per page for a PDF
    (first MAX_PAGES_PER_FILE pages). Messages for the user, such as truncation, are appended to `notes`."""
    data = uploaded.getvalue()
    if not uploaded.name.lower().endswith(".pdf"):
        return [Image.open(io.BytesIO(data))]
    import pypdfium2 as pdfium  # imported here so the app still starts if it's missing
    pdf = pdfium.PdfDocument(data)
    total = len(pdf)
    if total > MAX_PAGES_PER_FILE:
        notes.append(f"{uploaded.name} has {total} pages; only the first {MAX_PAGES_PER_FILE} were used.")
    return [pdf[i].render(scale=1.5).to_pil().convert("RGB") for i in range(min(total, MAX_PAGES_PER_FILE))]
