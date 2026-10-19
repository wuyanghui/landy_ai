"""POST /api/v2/invoke/market: the price-page chat, shaped like the listing chat's /api/v2/invoke/slug."""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage


def _fake_postgres(*a, **kw):
    cp = AsyncMock()
    cp.__aenter__ = AsyncMock(return_value=cp)
    cp.__aexit__ = AsyncMock(return_value=None)
    cp.setup = AsyncMock()
    return cp


def _agent(answer, turns=1):
    history = []
    for _ in range(turns):
        history += [HumanMessage(content="q"), AIMessage(content=answer)]
    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={"messages": history})
    return agent


def test_answers_about_the_page(shah_alam_page):
    from src.index import app

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres), \
         patch("agent.market.data.fetch_page", return_value=shah_alam_page) as fetch, \
         patch("agent.market.orchestration.create_market_agent", return_value=_agent("Typically RM 731 per sq ft.")) as make:
        resp = TestClient(app).post("/api/v2/invoke/market", json={
            "message": "how much is a factory here?", "property_class": "industrial", "path": "selangor/shah-alam",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["graph_output"] == "Typically RM 731 per sq ft."
    assert body["thread_id"]
    assert body["follow_up_suggestions"] == []
    fetch.assert_called_once_with("industrial", "selangor/shah-alam")
    assert make.call_args.args[0] is shah_alam_page


def test_keeps_the_thread(shah_alam_page):
    from src.index import app

    agent = _agent("ok")
    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres), \
         patch("agent.market.data.fetch_page", return_value=shah_alam_page), \
         patch("agent.market.orchestration.create_market_agent", return_value=agent):
        resp = TestClient(app).post("/api/v2/invoke/market", json={
            "message": "and Klang?", "property_class": "industrial", "path": "selangor/shah-alam", "thread_id": "t-1",
        })
    assert resp.json()["thread_id"] == "t-1"
    assert agent.ainvoke.call_args.args[1] == {"configurable": {"thread_id": "t-1"}}


def test_rejects_an_empty_message():
    from src.index import app

    resp = TestClient(app).post("/api/v2/invoke/market", json={"message": "", "property_class": "industrial", "path": ""})
    assert resp.status_code == 400


def test_rejects_an_unknown_class():
    from src.index import app

    resp = TestClient(app).post("/api/v2/invoke/market", json={"message": "hi", "property_class": "condo", "path": ""})
    assert resp.status_code == 400


def test_404_when_the_page_does_not_exist():
    from src.index import app

    with patch("agent.market.data.fetch_page", return_value=None):
        resp = TestClient(app).post("/api/v2/invoke/market", json={
            "message": "hi", "property_class": "industrial", "path": "selangor/nowhere",
        })
    assert resp.status_code == 404


def test_errors_do_not_leak_a_traceback(shah_alam_page):
    from src.index import app

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres), \
         patch("agent.market.data.fetch_page", return_value=shah_alam_page), \
         patch("agent.market.orchestration.create_market_agent", side_effect=RuntimeError("boom")):
        resp = TestClient(app).post("/api/v2/invoke/market", json={
            "message": "hi", "property_class": "industrial", "path": "selangor/shah-alam",
        })
    assert resp.status_code == 500
    assert "traceback" not in resp.json()


def _ask(page, agent):
    from src.index import app

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres), \
         patch("agent.market.data.fetch_page", return_value=page), \
         patch("agent.market.orchestration.create_market_agent", return_value=agent):
        return TestClient(app).post("/api/v2/invoke/market", json={
            "message": "q", "property_class": "industrial", "path": "selangor/shah-alam", "thread_id": "t",
        }).json()


def test_no_contact_card_on_a_first_plain_question(shah_alam_page):
    assert _ask(shah_alam_page, _agent("Typically RM 731 per sq ft."))["agent_referral_shown"] is False


def test_contact_card_on_the_third_message(shah_alam_page):
    assert _ask(shah_alam_page, _agent("RM 731.", turns=3))["agent_referral_shown"] is True


def test_contact_card_when_the_answer_offers_jay(shah_alam_page):
    answer = "**Next step:** WhatsApp Jay Kew (+6011-33199291) for a free price check on your property."
    assert _ask(shah_alam_page, _agent(answer))["agent_referral_shown"] is True
