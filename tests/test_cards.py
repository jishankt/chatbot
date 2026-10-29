import pytest
from app.agent.pipeline import CX02Pipeline

def test_printers_cards_4_items():
    p = CX02Pipeline()
    for q in ["Show me photo printers", "printers like cx 02", "items like cx 02", "printer"]:
        res = p.process(q, sender_id=f"test_printer_cards_{hash(q)}")
        cards = res.get("cards", [])
        assert len(cards) == 4, f"Expected 4 printer cards for '{q}', got {len(cards)}"
        skus = [c["sku"] for c in cards]
        assert "CX-02" in skus
        assert "CX-02W" in skus
        assert "CY-02" in skus
        assert "CZ-01" in skus

def test_consumables_cards_4_items():
    p = CX02Pipeline()
    for q in ["Show me consumables", "consumables like cx 02", "media rolls"]:
        res = p.process(q, sender_id=f"test_consumable_cards_{hash(q)}")
        cards = res.get("cards", [])
        assert len(cards) == 4, f"Expected 4 consumable cards for '{q}', got {len(cards)}"
        skus = [c["sku"] for c in cards]
        assert "CX2-MS46-2PC" in skus
        assert "CX2-MS57-2PC" in skus
        assert "CX2-MS68-2PC" in skus
        assert "CITIZEN-PEN" in skus
