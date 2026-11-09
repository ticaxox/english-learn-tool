from __future__ import annotations

from tests.ai_support import create_provider, fake_provider_server, login

ADMIN_PATH = "/api/v1/admin/knowledge"
SEARCH_PATH = "/api/v1/knowledge/search"

EXAM_TEXT = """2023 年 6 月 四级 阅读
1. What is the main idea of the passage?
A. The night market brings people together.
B. The night market is closing.
C. Food is expensive.
D. Nobody visits.
答案：A
解析：文章反复强调夜市让邻里聚在一起。

2. Why did Lin return?
A. To find work.
B. To revisit the market she loved.
C. To sell her house.
D. To meet a teacher.
答案：B
解析：她说想再看看小时候的夜市。

3. What does "harbor" mean here?
A. 港口
B. 保护
C. 藏匿
D. 停泊
答案：B
解析：harbor 在这里作动词，表示怀有、保留。
"""


async def test_admin_imports_and_learners_search(client, admin_user, member_user) -> None:
    admin_headers = await login(client, admin_user.username)
    member_headers = await login(client, member_user.username)

    imported = await client.post(
        ADMIN_PATH,
        headers=admin_headers,
        json={
            "source_type": "exam",
            "title": "2023-06 四级阅读",
            "content": EXAM_TEXT,
            "metadata": {"year": 2023, "exam": "CET4"},
        },
    )
    assert imported.status_code == 201, imported.text
    document = imported.json()
    assert document["status"] == "ready"
    assert document["chunk_count"] >= 1
    assert document["metadata"]["exam"] == "CET4"

    listed = await client.get(ADMIN_PATH, headers=admin_headers)
    assert [item["id"] for item in listed.json()["items"]] == [document["id"]]

    found = await client.get(
        SEARCH_PATH, headers=member_headers, params={"query": "night market harbor"}
    )
    assert found.status_code == 200, found.text
    hits = found.json()["items"]
    assert hits, found.text
    assert hits[0]["title"] == "2023-06 四级阅读"
    assert "夜市" in hits[0]["content"] or "harbor" in hits[0]["content"].lower()
    assert hits[0]["score"] > 0


async def test_members_cannot_import_or_list_documents(client, member_user) -> None:
    headers = await login(client, member_user.username)
    rejected = await client.post(
        ADMIN_PATH,
        headers=headers,
        json={"source_type": "exam", "title": "x", "content": "hello world"},
    )
    assert rejected.status_code == 403
    listed = await client.get(ADMIN_PATH, headers=headers)
    assert listed.status_code == 403


async def test_archiving_removes_the_document_from_search(client, admin_user, member_user) -> None:
    admin_headers = await login(client, admin_user.username)
    member_headers = await login(client, member_user.username)
    created = await client.post(
        ADMIN_PATH,
        headers=admin_headers,
        json={"source_type": "exam", "title": "待下架", "content": EXAM_TEXT},
    )
    document_id = created.json()["id"]

    removed = await client.delete(f"{ADMIN_PATH}/{document_id}", headers=admin_headers)
    assert removed.status_code == 204

    after = await client.get(
        SEARCH_PATH, headers=member_headers, params={"query": "night market"}
    )
    assert after.json()["items"] == []


async def test_search_returns_nothing_for_unrelated_queries(
    client, admin_user, member_user
) -> None:
    admin_headers = await login(client, admin_user.username)
    member_headers = await login(client, member_user.username)
    await client.post(
        ADMIN_PATH,
        headers=admin_headers,
        json={"source_type": "exam", "title": "阅读", "content": EXAM_TEXT},
    )
    empty = await client.get(
        SEARCH_PATH, headers=member_headers, params={"query": "photosynthesis chlorophyll"}
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []


async def test_mcp_can_search_the_knowledge_base(client, admin_user, member_user) -> None:
    admin_headers = await login(client, admin_user.username)
    await client.post(
        ADMIN_PATH,
        headers=admin_headers,
        json={"source_type": "exam", "title": "真题", "content": EXAM_TEXT},
    )
    member_headers = await login(client, member_user.username)
    created = await client.post(
        "/api/v1/me/tokens", headers=member_headers, json={"name": "Claude"}
    )
    token = created.json()["token"]
    called = await client.post(
        "/api/v1/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_knowledge",
                "arguments": {"query": "night market", "limit": 3},
            },
        },
    )
    result = called.json()["result"]
    assert result["isError"] is False, result
    assert "夜市" in result["content"][0]["text"] or "night" in result["content"][0]["text"].lower()


async def test_import_can_use_a_provider_embedding_model(client, admin_user) -> None:
    admin_headers = await login(client, admin_user.username)
    with fake_provider_server() as server:
        await create_provider(client, admin_headers, base_url=server.base_url)
        server.queue_json(
            200,
            {
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                ]
            },
        )
        # The provider has no embedding_model configured, so import stays keyword-only.
        imported = await client.post(
            ADMIN_PATH,
            headers=admin_headers,
            json={"source_type": "exam", "title": "无向量", "content": EXAM_TEXT},
        )
    assert imported.status_code == 201, imported.text
    assert imported.json()["embedding_model"] is None
