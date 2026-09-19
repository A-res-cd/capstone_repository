from app.utils.cor_extractor import parse_cor_text


def test_parse_cor_template_fields():
    fields = parse_cor_text(
        "RegistrationNo: 5361807\n"
        "Name: SAPIN,AARIESM.\n"
        "Student No: SUM 2023-01246"
    )

    assert fields == {
        "registration_no": "5361807",
        "student_no": "SUM2023-01246",
        "first_name": "Aaries",
        "middle_name": "M",
        "last_name": "Sapin",
    }


def test_parse_cor_ocr_name_without_comma_and_with_adjacent_program():
    fields = parse_cor_text(
        "RegistrationNo: 5361807 Sumacab Campus AcademicYearterm: 2026-2027\n"
        "Name: SAPIN AARIESM. Program: Bachelor of Science in Information Technology"
    )

    assert fields["registration_no"] == "5361807"
    assert fields["first_name"] == "Aaries"
    assert fields["middle_name"] == "M"
    assert fields["last_name"] == "Sapin"
