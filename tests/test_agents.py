"""agent 指派机制单元测试：只测 runner 生成与配置解析，零 API 成本。

覆盖：
  1. runner_script 三种提示词传递方式（stdin/atfile/argvfile）生成正确的 shell 行；
  2. resolve_agent 的三层显式配置优先级与 fail-loud 行为（无默认，缺失即 SystemExit）；
  3. 命令行 --codex-command 覆盖（负面测试桩依赖的路径）；
  4. roles 有序列表解析（failover 依序项）与 csv 逗号列表；
  5. infralike 双轨判别器（秒死/标记字）——A 的零 API 核心。
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import remote_agent  # noqa: E402
import controller  # noqa: E402


class TestHostBuildRemote(unittest.TestCase):
    """Host.build_remote：远端命令串构造，重点 pre_cmd 前置注入与 ~ 远端展开。"""

    def test_no_pre_cmd(self):
        out = controller.Host.build_remote("", "python3", "~/codex_v4pro/remote_agent.py", "check", False)
        # 双引号 + $HOME：单引号会把 ~ 冻结在远端 shell，导致 FileNotFoundError
        self.assertEqual(out, '"python3" "$HOME/codex_v4pro/remote_agent.py" check')

    def test_with_pre_cmd(self):
        pre = "export PATH=$HOME/local/bin:$PATH; . $HOME/.pi_agent_env 2>/dev/null;"
        out = controller.Host.build_remote(pre, "python3", "~/codex_v4pro/remote_agent.py", "start", True)
        self.assertTrue(out.startswith(pre + " "))
        self.assertTrue(out.endswith("start --payload-stdin"))

    def test_pre_cmd_whitespace_only(self):
        out = controller.Host.build_remote("   ", "python3", "~/codex_v4pro/remote_agent.py", "check", False)
        self.assertEqual(out, '"python3" "$HOME/codex_v4pro/remote_agent.py" check')

    def test_remote_quote_abs_path_untouched(self):
        self.assertEqual(controller.Host.remote_quote("/root/codex_v4pro"), '"/root/codex_v4pro"')

    def test_remote_quote_tilde_becomes_home(self):
        self.assertEqual(controller.Host.remote_quote("~/codex_v4pro"), '"$HOME/codex_v4pro"')


def base_cfg() -> dict:
    return {"agents": {
        "presets": {
            "codex": {"cmd": "codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check", "style": "stdin"},
            "pi": {"cmd": "pi -p --no-session", "style": "atfile"},
            "pi-kimi": {"cmd": "pi-kimi -p --no-session", "style": "atfile"},
        },
        "roles": {"coder": "codex", "fix": "codex", "review": "pi-kimi"},
    }}


def fake_task(agents=None) -> controller.Task:
    return controller.Task(task_id="7", project="kwant_demo", worker="local",
                           task_file=Path("tasks/task_numkit_simple.md"), agents=agents or {})


class TestRunScriptAgentLines(unittest.TestCase):
    """runner_script 的输出行决定工人实际怎么吃到提示词。"""

    def render(self, style: str, cmd: str, role: str = "review") -> str:
        with tempfile.TemporaryDirectory() as d:
            td = Path(d) / "task-1"
            logs = td / "logs"
            logs.mkdir(parents=True)
            (logs / f"{role}_r1_prompt.md").write_text("hello world", encoding="utf-8")
            payload = {"task_dir": str(td), "agent_cmd": cmd, "agent_style": style,
                       "agent_name": "pi-kimi", "timeout_seconds": None}
            return remote_agent.runner_script(payload, role, 1, Path(d) / "ws")

    def test_stdin_appends_dash_and_redirects_prompt(self):
        s = self.render("stdin", "codex exec --skip-git-repo-check")
        self.assertIn("exec --skip-git-repo-check - < ", s)
        self.assertIn("review_r1_prompt.md", s)
        self.assertIn(">> ", s)  # 日志重定向
        self.assertIn("mark-done", s)

    def test_stdin_keeps_existing_dash_unchanged(self):
        s = self.render("stdin", "codex exec -")
        self.assertIn("exec - < ", s)
        self.assertNotIn("- - <", s)

    def test_atfile_passes_prompt_as_file_arg(self):
        s = self.render("atfile", "pi -p --no-session")
        self.assertIsNotNone(re.search(r'"?pi"? -p --no-session @\S*review_r1_prompt\.md', s),
                             f"未找到 @prompt 参数形式：{s}")

    def test_atfile_quotes_path_with_spaces(self):
        # 路径含空格时 @参数必须是单引号包裹的单个 argv，不能被 shell 拆开
        with tempfile.TemporaryDirectory(prefix="pi test ") as d:
            td = Path(d) / "task-1"
            logs = td / "logs"
            logs.mkdir(parents=True)
            (logs / "review_r1_prompt.md").write_text("hi", encoding="utf-8")
            payload = {"task_dir": str(td), "agent_cmd": "pi -p --no-session",
                       "agent_style": "atfile", "agent_name": "pi", "timeout_seconds": None}
            s = remote_agent.runner_script(payload, "review", 1, Path(d) / "ws")
        self.assertIsNotNone(re.search(r"'@[^']*review_r1_prompt\.md'", s),
                             f"@路径未被引号包裹：{s}")

    def test_argvfile_wraps_into_command_substitution(self):
        s = self.render("argvfile", "pi -p --no-session")
        self.assertIsNotNone(re.search(r'-p --no-session "\$\(cat \S*review_r1_prompt\.md\)"', s),
                             f"未找到 $(cat ...) 参数形式：{s}")

    def test_unknown_style_raises(self):
        with self.assertRaisesRegex(RuntimeError, "未知 agent style"):
            self.render("telepathy", "pi -p")

    def test_missing_agent_cmd_raises(self):
        with tempfile.TemporaryDirectory() as d:
            td = Path(d) / "task-1"
            logs = td / "logs"
            logs.mkdir(parents=True)
            (logs / "coder_r1_prompt.md").write_text("hi", encoding="utf-8")
            payload = {"task_dir": str(td), "agent_style": "stdin"}
            with self.assertRaisesRegex(RuntimeError, "agent_cmd"):
                remote_agent.runner_script(payload, "coder", 1, Path(d) / "ws")


class TestResolveAgent(unittest.TestCase):
    """强制显式选择：每一层缺失都要 fail-loud，没有静默默认。"""

    def test_config_roles_mapping(self):
        a = controller.resolve_agent(base_cfg(), fake_task(), "review")
        self.assertEqual(a, {"name": "pi-kimi", "cmd": "pi-kimi -p --no-session", "style": "atfile"})
        for role in ("coder", "fix"):
            self.assertEqual(controller.resolve_agent(base_cfg(), fake_task(), role)["name"], "codex")

    def test_csv_column_overrides_roles(self):
        a = controller.resolve_agent(base_cfg(), fake_task({"review": "pi"}), "review")
        self.assertEqual(a["name"], "pi")
        self.assertEqual(a["cmd"], "pi -p --no-session")

    def test_cli_codex_command_overrides_everything(self):
        cfg = {"codex_command": "FAKE_BAD_MODE=n1 python3 test_fake_codex_bad.py"}
        for role in controller.AGENT_ROLES:
            a = controller.resolve_agent(cfg, fake_task(), role)
            self.assertEqual(a["name"], "codex")
            self.assertEqual(a["style"], "stdin")
            self.assertEqual(a["cmd"], cfg["codex_command"])

    def test_no_config_no_task_column_fails_loud(self):
        with self.assertRaisesRegex(SystemExit, "review.*没有显式指定"):
            controller.resolve_agent({}, fake_task(), "review")

    def test_unknown_preset_fails_loud(self):
        cfg = base_cfg()
        cfg["agents"]["roles"]["review"] = "nope"
        with self.assertRaisesRegex(SystemExit, "未知 preset 'nope'"):
            controller.resolve_agent(cfg, fake_task(), "review")

    def test_bad_style_fails_loud(self):
        cfg = base_cfg()
        cfg["agents"]["presets"]["codex"]["style"] = "telepathy"
        with self.assertRaisesRegex(SystemExit, "style 'telepathy'"):
            controller.resolve_agent(cfg, fake_task(), "coder")

    def test_empty_cmd_fails_loud(self):
        cfg = base_cfg()
        cfg["agents"]["presets"]["codex"]["cmd"] = ""
        with self.assertRaisesRegex(SystemExit, "cmd 为空"):
            controller.resolve_agent(cfg, fake_task(), "coder")


class TestResolveAgentsLists(unittest.TestCase):
    """A：roles 变有序列表，失效依序项；单值/逗号串保持向后兼容。"""

    def test_roles_list_preserves_order(self):
        cfg = base_cfg()
        cfg["agents"]["roles"]["review"] = ["pi-kimi", "codex"]
        a = controller.resolve_agents(cfg, fake_task(), "review")
        self.assertEqual([x["name"] for x in a], ["pi-kimi", "codex"])
        self.assertEqual(a[0]["style"], "atfile")
        self.assertEqual(a[1]["style"], "stdin")

    def test_csv_column_comma_list(self):
        cfg = base_cfg()
        a = controller.resolve_agents(cfg, fake_task({"review": "pi-kimi, codex"}), "review")
        self.assertEqual([x["name"] for x in a], ["pi-kimi", "codex"])

    def test_roles_list_with_unknown_preset_fails(self):
        cfg = base_cfg()
        cfg["agents"]["roles"]["review"] = ["pi-kimi", "nope"]
        with self.assertRaisesRegex(SystemExit, "未知 preset 'nope'"):
            controller.resolve_agents(cfg, fake_task(), "review")

    def test_roles_list_empty_fails(self):
        cfg = base_cfg()
        cfg["agents"]["roles"]["review"] = ["  "]
        with self.assertRaisesRegex(SystemExit, "没有显式指定"):
            controller.resolve_agents(cfg, fake_task(), "review")

    def test_compat_resolve_agent_is_first_of_list(self):
        cfg = base_cfg()
        cfg["agents"]["roles"]["review"] = ["pi-kimi", "codex"]
        a = controller.resolve_agent(cfg, fake_task(), "review")
        self.assertEqual(a, {"name": "pi-kimi", "cmd": "pi-kimi -p --no-session", "style": "atfile"})


class TestInfralike(unittest.TestCase):
    """A 双轨判别器：infra（换 agent 重开）vs real（保持 fail-loud）。"""

    def make(self, **kw):
        base = {"duration_seconds": None, "log_bytes": 0, "log_tail": ""}
        base.update(kw)
        return base

    def test_fast_death_is_infra(self):
        # 17 秒就死掉且日志 100 字节：还没来得及产出真内容
        self.assertTrue(controller.infralike(self.make(duration_seconds=17, log_bytes=100)))

    def test_seconds_death_with_large_log_is_real(self):
        # 死得虽快但写了 2KiB：可能是真干砸（如环境炸）→ 不能乱换 agent 淹没证据
        self.assertFalse(controller.infralike(self.make(duration_seconds=17, log_bytes=2048)))

    def test_long_then_connection_error_is_infra(self):
        # vina 证物形态：干了 16.7 分钟后才 Connection error → 标记字命中
        self.assertTrue(controller.infralike(
            self.make(duration_seconds=1002, log_bytes=55, log_tail="Connection error.")))

    def test_404_marker_is_infra(self):
        self.assertTrue(controller.infralike(
            self.make(duration_seconds=60, log_bytes=500, log_tail="HTTP 404 Not Found")))

    def test_marker_with_unknown_duration_still_infra(self):
        # 标记字规则不依赖时长取数：duration 缺失时只要日志有断通路短语仍判 infra
        # （探 wolf 证物形态：旧状态文件没有 started/finished 戳也应按强证据走）
        self.assertTrue(controller.infralike(
            self.make(duration_seconds=None, log_bytes=55, log_tail="Connection error.")))

    def test_nothing_known_is_real(self):
        # 时长缺失且无标记字：不能证明 infra → 按真死算，fail-loud 不被软化
        self.assertFalse(controller.infralike(self.make(duration_seconds=None)))

    def test_real_crash_stays_real(self):
        self.assertFalse(controller.infralike(
            self.make(duration_seconds=50, log_bytes=12000, log_tail="TypeError: 'NoneType' object")))


if __name__ == "__main__":
    unittest.main()

class TestCleanDir(unittest.TestCase):
    """cmd_clean_dir：worker 侧清空 coder 工作区（R1 修复的后端命令）。"""

    def test_cleans_polluted_dir(self):
        with tempfile.TemporaryDirectory() as d:
            wr = Path(d) / "work"
            tgt = wr / "project_x"
            tgt.mkdir(parents=True)
            (tgt / "half_done.py").write_text("partial")
            remote_agent.cmd_clean_dir({"dir": str(tgt), "work_root": str(wr)})
            self.assertTrue(tgt.is_dir())
            self.assertEqual(list(tgt.iterdir()), [])

    def test_rejects_outside_work_root(self):
        with tempfile.TemporaryDirectory() as d:
            wr = Path(d) / "work"
            wr.mkdir()
            outside = str(Path(d) / "precious")
            remote_agent.cmd_clean_dir({"dir": outside, "work_root": str(wr)})
            # 拒绝清理时不应创建/删除任何东西（outside 默认本来就不存在）
            self.assertFalse(Path(outside).exists())


class TestAgentCommandLineEnvPrefix(unittest.TestCase):
    """env 前缀（VAR=val cmd ...）不能被首词双引号冻结成 execvp 目标。"""

    def test_env_prefix_atfile(self):
        line = remote_agent.agent_command_line(
            "FAKE_PI_MODE=ok python3 /tmp/fake_pi.py", "atfile",
            Path("/tmp/p.md"))
        self.assertTrue(line.startswith("FAKE_PI_MODE=ok \"python3\" /tmp/fake_pi.py"),
                        f"got: {line}")

    def test_env_prefix_stdin(self):
        line = remote_agent.agent_command_line(
            "A=1 B=2 python3 /tmp/fake_codex.py", "stdin",
            Path("/tmp/p.md"))
        self.assertTrue(line.startswith("A=1 B=2 \"python3\" /tmp/fake_codex.py"),
                        f"got: {line}")


class TestInfraReopenCleanDir(unittest.TestCase):
    """R1：coder infra failover 必须委托 worker 清空工作区（不是本机 rmtree）。"""

    def test_coder_infra_reopen_calls_clean_dir(self):
        cfg = {
            "remote_agent_dir": "/ra",
            "remote_python": "python3",
            "repo": {"owner": "testowner", "suffix": "_t"},
            "work_root": "/wr",
            "policy_file": None,
            "agents": {"roles": {"coder": ["a-bad", "b-ok"], "review": ["r"],
                                 "fix": ["f"]},
                       "presets": {"a-bad": {"cmd": "false", "style": "stdin",
                                             "probe": {}},
                                   "b-ok": {"cmd": "true", "style": "stdin", "probe": {}},
                                   "r": {"cmd": "true", "style": "stdin", "probe": {}},
                                   "f": {"cmd": "true", "style": "stdin", "probe": {}}}},
            "failover_cap": 3,
        }
        tc = controller.Task(task_id="1", project="p", worker="local",
                             task_file=Path("/x.md"), timeout_minutes=5,
                             max_fix_rounds=2, agents=cfg["agents"])
        r = controller.Runner(cfg)
        r.tasks = [tc]
        calls = []

        class _FakeHost:
            def __init__(self, calls):
                self._calls = calls

            def agent(self, cmd, payload=None, timeout=None):
                self._calls.append((cmd, payload or {}))
                return {} if cmd == "reset-phase" else {"ok": True}

        r.host = lambda name: _FakeHost(calls)
        t = tc
        st = r.state.setdefault(str(t.task_id), {})
        st.update({"phase": "coder_running", "failovers": 0, "coder_agent_idx": 0})
        r._infra_reopen(t, "coder", reason="rc=3, dur=0s")
        self.assertEqual(st["phase"], "coder_pending")
        self.assertEqual(st["failovers"], 1)
        cmds = [c for c in calls if c[0] == "clean-dir"]
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0][1].get("dir"), r.coder_dir(t))
        self.assertEqual(cmds[0][1].get("work_root"), r.work_root())
