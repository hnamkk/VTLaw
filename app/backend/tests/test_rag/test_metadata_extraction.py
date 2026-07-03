from src.rag.metadata_extraction import (
    build_canonical_title,
    extract_document_number_candidate,
    extract_effective_date_candidate,
    infer_document_number_from_filename,
)
from src.rag.retrieval.query_utils import expand_query_for_retrieval, query_for_local_ranking


def test_extract_document_number_candidate_from_preview_text():
    text = """
    QUOC HOI
    Luat so: 118/2025/QH15
    LUAT
    """
    assert extract_document_number_candidate(text) == "118/2025/QH15"


def test_infer_document_number_from_filename():
    assert infer_document_number_from_filename("336_2025_ND-CP_670893.docx") == "336/2025/NĐ-CP"


def test_build_canonical_title_uses_document_number():
    assert (
        build_canonical_title("NGHI_DINH", "336/2025/NĐ-CP", "Generic title")
        == "Nghị định 336/2025/NĐ-CP"
    )


def test_effective_date_prefers_formal_section_over_transitional_dates():
    text = """
    Điều 76. Điều khoản chuyển tiếp
    Kể từ ngày 01 tháng 01 năm 2026, đơn vị phải đáp ứng điều kiện mới.
    Điều 77. Hiệu lực thi hành
    1. Nghị định này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.
    """

    assert extract_effective_date_candidate(text).isoformat() == "2025-01-01"


def test_expand_query_for_retrieval_adds_transport_permit_hints():
    query = "Xe tai 15 tan chay tuyen lien tinh can giay to gi?"
    expanded = expand_query_for_retrieval(query)
    assert expanded != query
    assert "giay phep kinh doanh van tai" in expanded
    assert "phu hieu" in expanded


def test_expand_query_for_retrieval_adds_gpkd_hints_without_vehicle():
    query = "Dieu kien cap GPKD van tai hang hoa la gi?"
    expanded = expand_query_for_retrieval(query)
    assert expanded != query
    assert "giay phep kinh doanh van tai" in expanded


def test_expand_query_for_retrieval_adds_safe_distance_hints():
    query = "Khoang cach an toan giua xe tai toc do 60km/h la bao nhieu met?"
    expanded = expand_query_for_retrieval(query)
    assert expanded != query
    assert "khoang cach an toan" in expanded


def test_expand_query_for_retrieval_adds_phone_prohibition_hints():
    query = "Tai xe xe tai nang duoc phep su dung dien thoai khi lai xe khong?"
    expanded = expand_query_for_retrieval(query)
    assert expanded != query
    assert "dung tay cam va su dung dien thoai" in expanded


def test_expand_query_for_retrieval_maps_everyday_penalty_language():
    assert "đèn tín hiệu giao thông" in expand_query_for_retrieval("Mức phạt vượt đèn đỏ?")
    assert "không đội mũ bảo hiểm" in expand_query_for_retrieval("Xe máy không đội mũ bị phạt?")
    assert "không có giấy phép lái xe" in expand_query_for_retrieval("Không có bằng lái xe máy")
    assert "đèn chiếu xa" in expand_query_for_retrieval("Dùng đèn pha gặp xe ngược chiều")
    assert "nồng độ cồn" in expand_query_for_retrieval("Uống rượu lái xe máy")
    assert "đường một chiều" in expand_query_for_retrieval("Xe máy đi ngược chiều")


def test_expand_query_for_camera_and_driving_time():
    expanded = expand_query_for_retrieval(
        "Tài xế lái tối đa bao nhiêu giờ/ngày và xe 9 chỗ có cần camera không?"
    )

    assert "phải lắp camera" in expanded
    assert "không quá 10 giờ trong một ngày" in expanded


def test_local_ranking_query_removes_document_reference_but_keeps_behavior():
    query = query_for_local_ranking("Mức phạt vượt đèn đỏ theo NĐ 100/2019 hiện nay?")

    assert "100/2019" not in query
    assert "vượt đèn đỏ" in query
