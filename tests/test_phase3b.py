import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from models.orm import Provider, Client
from orchestrator.central import CentralOrchestrator
from orchestrator.agent import ClientAgent


def _make_provider() -> Provider:
    p = Provider()
    p.id = 1
    p.name = "Kaushik"
    p.phone_number = "+15550000000"
    p.business_type = "personal_training"
    return p


def _make_client(name="Sarah", phone="+15550001111", status="active") -> Client:
    c = Client()
    c.id = 10
    c.name = name
    c.phone_number = phone
    c.status = status
    c.notes = None
    return c


def _make_messaging():
    m = MagicMock()
    m.send_to_admin = AsyncMock()
    m.send_to_phone = AsyncMock()
    return m


def test_orchestrator_instantiates():
    messaging = _make_messaging()
    orch = CentralOrchestrator(messaging, {"business_type": "personal_training"})
    assert orch._provider is None
    assert orch._agents == {}


def test_client_agent_instantiates():
    provider = _make_provider()
    client = _make_client()
    messaging = _make_messaging()
    agent = ClientAgent(
        phone="+15550001111",
        client=client,
        provider=provider,
        messaging_client=messaging,
        business_config={"business_type": "personal_training"},
    )
    assert agent.phone == "+15550001111"
    assert agent._history == []
    assert agent._turn_count == 0


def test_orchestrator_routes_admin():
    messaging = _make_messaging()
    provider = _make_provider()
    orch = CentralOrchestrator(messaging, {"business_type": "personal_training"})
    orch._provider = provider
    orch._admin_agent = MagicMock()
    orch._admin_agent.handle_message = AsyncMock()

    mock_db = MagicMock()
    mock_conv_store = MagicMock()
    mock_state = MagicMock()
    mock_state.handoff_active = False
    mock_state.handoff_target_phone = None
    mock_state.context = {}
    mock_state.last_donna_message = None
    mock_conv_store.get_or_create.return_value = mock_state
    mock_conv_store.get_by_phone.return_value = mock_state
    mock_conv_store.get_history.return_value = []
    mock_conv_store.append_history = MagicMock()

    with patch("orchestrator.central.ConversationStore", return_value=mock_conv_store), \
         patch("orchestrator.central.ClientStore"), \
         patch("orchestrator.central.ProviderStore"):
        asyncio.run(orch.handle_message(provider.phone_number, "show me the schedule", mock_db))
        orch._admin_agent.handle_message.assert_called_once_with("show me the schedule", mock_db)


def test_orchestrator_spawns_agent_for_client():
    messaging = _make_messaging()
    provider = _make_provider()
    client = _make_client()
    orch = CentralOrchestrator(messaging, {"business_type": "personal_training"})
    orch._provider = provider
    orch._admin_agent = MagicMock()

    mock_db = MagicMock()
    mock_conv_store = MagicMock()
    mock_state = MagicMock()
    mock_state.handoff_active = False
    mock_conv_store.get_by_phone.return_value = mock_state
    mock_conv_store.get_or_create.return_value = mock_state
    mock_conv_store.append_history = MagicMock()

    mock_client_store = MagicMock()
    mock_client_store.get_by_phone.return_value = client

    mock_agent = MagicMock()
    mock_agent.handle_message = AsyncMock()

    with patch("orchestrator.central.ConversationStore", return_value=mock_conv_store), \
         patch("orchestrator.central.ClientStore", return_value=mock_client_store), \
         patch("orchestrator.central.ProviderStore"), \
         patch.object(orch, "_get_or_spawn_agent", new=AsyncMock(return_value=mock_agent)):
        asyncio.run(orch.handle_message(client.phone_number, "hi", mock_db))
        mock_agent.handle_message.assert_called_once_with("hi", mock_db)


def test_retire_agent():
    messaging = _make_messaging()
    provider = _make_provider()
    client = _make_client()
    orch = CentralOrchestrator(messaging, {"business_type": "personal_training"})
    orch._provider = provider

    agent = ClientAgent(
        phone=client.phone_number,
        client=client,
        provider=provider,
        messaging_client=messaging,
        business_config={},
    )
    orch._agents[client.phone_number] = agent
    assert client.phone_number in orch._agents

    orch.retire_agent(client.phone_number)
    assert client.phone_number not in orch._agents
    orch.retire_agent(client.phone_number)  # idempotent
