from pojok_literasi_mcp.anti_ai import periksa, ringkas


def test_naskah_ala_ai_ditandai():
    naskah = (
        "Di era digital ini, membaca menjadi permata tersembunyi.\n"
        "Mari kita selami buku ini bersama.\n"
        "Pada akhirnya, buku ini sangat direkomendasikan."
    )
    hasil = ringkas(periksa(naskah))
    assert hasil.startswith("PERLU REVISI")
    assert "permata tersembunyi" in hasil
    assert "detail pribadi" in hasil


def test_naskah_pribadi_lolos():
    naskah = (
        "Aku baca buku ini pas lagi nunggu kereta di Manggarai.\n"
        "Jujur, bab tiga bikin aku kesel sama tokoh utamanya.\n"
        "Menurutku endingnya terlalu buru-buru."
    )
    assert periksa(naskah) == []
