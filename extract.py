from app.utils.pdf_extractor import extract_capstone_data

data = extract_capstone_data("instance/uploads/manuscripts/EvalOn_Manuscript.pdf")
print(f"Extracted capstone data: {data}")
