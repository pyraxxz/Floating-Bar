from types import SimpleNamespace

from floatingbar.recent_targets import RecentTargetHistory
from floatingbar.transaction import TargetScope


def test_recent_history_moves_reselected_target_to_front_and_caps_size():
    history = RecentTargetHistory(limit=2)
    history.record_application(
        hwnd=10, pid=100, process_name="one.exe", label="One", adapter_key="one"
    )
    history.record_application(
        hwnd=20, pid=200, process_name="two.exe", label="Two", adapter_key="two"
    )
    history.record_application(
        hwnd=10, pid=100, process_name="one.exe", label="One", adapter_key="one"
    )
    history.record_application(
        hwnd=30, pid=300, process_name="three.exe", label="Three", adapter_key="three"
    )

    assert [item.scope for item in history.items()] == [
        TargetScope(30, 300),
        TargetScope(10, 100),
    ]


def test_recent_application_validation_requires_exact_scope_and_adapter(monkeypatch):
    history = RecentTargetHistory()
    target = history.record_application(
        hwnd=44,
        pid=444,
        process_name="demo.exe",
        label="Demo",
        adapter_key="demo",
    )

    class User32:
        @staticmethod
        def IsWindow(hwnd):
            return hwnd == 44

    monkeypatch.setattr("floatingbar.recent_targets.winapi.user32", User32())
    monkeypatch.setattr(
        "floatingbar.recent_targets.winapi.get_window_pid",
        lambda hwnd: 444,
    )
    monkeypatch.setattr(
        "floatingbar.recent_targets.winapi.get_process_image_name",
        lambda pid: r"C:\\demo.exe",
    )
    monkeypatch.setattr(
        "floatingbar.recent_targets.actionable_adapter_for_process",
        lambda process: SimpleNamespace(implemented=True, key="demo"),
    )

    assert history.application_is_live(target)

    monkeypatch.setattr(
        "floatingbar.recent_targets.winapi.get_window_pid",
        lambda hwnd: 445,
    )
    assert not history.application_is_live(target)


def test_live_applications_discards_only_stale_app_entries(monkeypatch):
    history = RecentTargetHistory()
    live = history.record_application(
        hwnd=1, pid=10, process_name="live.exe", label="Live", adapter_key="live"
    )
    stale = history.record_application(
        hwnd=2, pid=20, process_name="stale.exe", label="Stale", adapter_key="stale"
    )
    monkeypatch.setattr(
        history,
        "application_is_live",
        lambda target: target == live,
    )

    assert history.live_applications() == (live,)
    assert stale not in history.items()


def test_recent_conversation_is_structurally_recorded():
    history = RecentTargetHistory()
    conversation = SimpleNamespace(
        hwnd=55,
        pid=555,
        name="Project Chat",
        runtime_id=(1, 2, 3),
        control_identity=("ListItem", "conversation"),
        left=10,
        top=20,
        right=250,
        bottom=52,
    )
    target = history.record_conversation(conversation, adapter_key="slack")

    assert target.kind == "conversation"
    assert target.label == "Project Chat"
    assert target.scope == TargetScope(55, 555)
    assert target.runtime_id == (1, 2, 3)
    assert target.control_identity == ("ListItem", "conversation")
    assert target.left == 10
    assert target.bottom == 52
