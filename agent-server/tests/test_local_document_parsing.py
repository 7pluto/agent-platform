import asyncio
import io
import zipfile

import pytest
from fastapi import UploadFile

from app.core.errors import ApiError
from app.knowledge.ingest import KnowledgeIngestor, _chunks
from app.knowledge.service import KnowledgeFileService


def _docx(text: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>',
        )
    return output.getvalue()


def _pdf(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, value in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{index} 0 obj\n".encode()); output.extend(value); output.extend(b"\nendobj\n")
    xref = len(output); output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets: output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def test_docx_validation_parse_and_chunk_preserve_chinese() -> None:
    content = _docx("本地员工手册规定：考勤异常应在两个工作日内提交说明。")
    upload = UploadFile(filename="员工考勤补充规定.docx", file=io.BytesIO(content))
    asyncio.run(KnowledgeFileService()._validate_uploaded_file(upload, upload.filename or ""))
    parsed = KnowledgeIngestor._parse(upload.filename or "", content)
    assert parsed == "本地员工手册规定：考勤异常应在两个工作日内提交说明。"
    assert _chunks(parsed) == [parsed]


def test_pdf_validation_and_parse_extract_business_text() -> None:
    content = _pdf("Employee attendance exceptions require an explanation within two working days.")
    upload = UploadFile(filename="employee-attendance.pdf", file=io.BytesIO(content))
    asyncio.run(KnowledgeFileService()._validate_uploaded_file(upload, upload.filename or ""))
    parsed = KnowledgeIngestor._parse(upload.filename or "", content)
    assert "attendance exceptions" in parsed
    assert "two working days" in parsed


def test_fake_docx_is_rejected_before_object_storage() -> None:
    upload = UploadFile(filename="伪造文档.docx", file=io.BytesIO(b"PK not-a-real-docx"))
    with pytest.raises(ApiError) as exc:
        asyncio.run(KnowledgeFileService()._validate_uploaded_file(upload, upload.filename or ""))
    assert exc.value.code == "INVALID_DOCUMENT_CONTENT"
