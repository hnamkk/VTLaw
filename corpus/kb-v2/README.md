# KB v2 Corpus Workspace

Thu muc nay chua corpus moi de re-upload vao KB v2.

Nguyen tac:

- Khong dat file vao `app/backend/storage/uploads` hoac storage KB v1 cu.
- Chi dung DOCX moi tai lai tu nguon co provenance ro.
- Ten file nen dung ASCII, lowercase, va co thu tu de de doi chieu.
- `corpus-checklist.csv` la ban text chuan de diff/import.
- `corpus-checklist.xlsx` la ban nhap lieu co dropdown cho cac cot gia tri co dinh.

Cau truc:

- `raw-docx/`: file DOCX theo batch.
- `notes/`: ghi chu nguon, quyet dinh review, va luu y corpus.

Gia tri nen dung:

- `priority`: `1`, `2`, `3`
- `role`: `base`, `amendment`, `replacement`, `guidance`, `foundation`, `technical`, `reference`

Quy uoc `depends_on`:

- De trong neu khong phu thuoc.
- Neu phu thuoc 1 van ban: ghi so hieu, vi du `100/2019/NĐ-CP`.
- Neu phu thuoc nhieu van ban: dung dau `;`, vi du `100/2019/NĐ-CP;36/2024/QH15`.
