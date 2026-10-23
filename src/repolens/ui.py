"""One workspace: local ingestion beside independent, source-backed questions."""

from html import escape
from pathlib import Path

import streamlit as st

from repolens.chunking import source_lines
from repolens.controller import create_controller
from repolens.domain import IndexStatus, Snippet
from repolens.errors import RepoLensError
from repolens.folder_picker import choose_repository_folder
from repolens.ui_style import HEADER, STYLE


def numbered_source(snippet: Snippet) -> str:
    """Display original file line numbers rather than restarting each snippet at 1."""
    return "\n".join(
        f"{number:4} {line.rstrip(chr(13) + chr(10))}"
        for number, line in enumerate(source_lines(snippet.text), snippet.start_line)
    )


def _index_card(status: IndexStatus, root: Path | None) -> None:
    """Escape local names before combining them with trusted status markup."""
    labels = {
        "missing": "No index",
        "ready": "Ready",
        "stale": "Rebuild required",
        "failed": "Index check failed",
    }
    descriptions = {
        "missing": "Build an index to enable questions.",
        "ready": "The index is ready for questions.",
        "stale": "Sources or embedding settings changed. Rebuild before asking.",
        "failed": "Check the details below, then rebuild if needed.",
    }
    counts = ""
    if status.snapshot:
        manifest = status.snapshot.manifest
        counts = (
            '<div class="rl-counts">'
            f"<div><strong>{len(manifest.file_hashes)}</strong>"
            "<small>Indexed files</small></div>"
            f"<div><strong>{manifest.snippet_count}</strong>"
            "<small>Snippets</small></div></div>"
        )
    st.html(
        f'<div class="rl-index {status.state}"><div class="rl-index-header">'
        f'<span class="rl-index-name">{escape(root.name if root else "Select a folder")}</span>'
        f'<span class="rl-badge">{labels[status.state]}</span></div>'
        f"<p>{descriptions[status.state]}</p>{counts}</div>"
    )
    if status.reason and status.state != "missing":
        st.info(status.reason)
    if status.snapshot:
        manifest = status.snapshot.manifest
        st.caption(f"Built {manifest.created_at} · {len(manifest.skipped)} skipped")
        if manifest.skipped:
            with st.expander("Skipped files and folders"):
                for skipped in manifest.skipped:
                    st.text(f"{skipped.relative_path}: {skipped.reason}")


def _empty_answer(status: IndexStatus, root: Path | None) -> None:
    """Explain the next step without displaying an answer from an old state."""
    if root is None:
        title, message = "Start with a repository", "Choose a folder in the left panel."
    elif status.state == "ready":
        title = "Your repository is ready"
        message = "Ask a question, then inspect the original supporting source lines."
    elif status.state == "stale":
        title, message = "Your index needs a refresh", "Rebuild in the left panel."
    else:
        title = "Build an index to get started"
        message = "Check the repository status in the left panel."
    st.html(f'<div class="rl-empty"><strong>{title}</strong><p>{message}</p></div>')


def render_app() -> None:
    """Compose the workspace while keeping all operations in existing services."""
    st.set_page_config(page_title="RepoLens", page_icon="🔎", layout="wide")
    st.html(STYLE)
    st.html(HEADER)
    # Session state survives Streamlit reruns; database handles remain per-operation.
    state = st.session_state
    try:
        if "controller" not in state:
            state.controller = create_controller()
    except RepoLensError as exc:
        st.error(str(exc))
        return
    controller = state.controller
    # A picker completes after widgets are rendered. Apply its result on the next
    # run, before constructing the root widget, to respect Streamlit's state rules.
    if "chosen_root" in state:
        state.root = state.pop("chosen_root")
    busy = bool(state.get("pending"))

    def queue(action):
        state.pending = action
        state.action_error = None
        # Cancelling Browse must preserve the current repository and answer.
        if action != "browse":
            state.answer = None

    ingestion, questions = st.columns([1, 2.1], gap="medium")
    repository_panel = ingestion.container(border=True, key="ingestion-panel")
    answer_panel = questions.container(border=True, key="answer-panel")
    with repository_panel:
        st.html('<div class="rl-eyebrow">01 / Ingestion</div>')
        st.subheader("Repository & index", anchor=False)
        st.html(
            '<p class="rl-panel-description">Choose the source behind your answers.</p>'
        )
        folder_controls = st.container(key="folder-control")
        folder_field, browse = folder_controls.columns([3, 1.5], gap="small")
        with folder_field:
            root_text = st.text_input(
                "Repository folder",
                key="root",
                disabled=busy or not state.get("manual_path", False),
                placeholder="Choose a local folder…",
            )
        with browse:
            st.html('<div class="rl-browse-spacer"></div>')
            st.button(
                "Browse…", key="browse", disabled=busy, on_click=queue, args=("browse",)
            )
        st.caption("Browse to select a local folder. Source files are read-only.")
        if state.get("folder_error"):
            st.error(state.folder_error)
        with st.expander("Folder options", expanded=bool(state.get("folder_error"))):
            st.checkbox("Enter path manually", key="manual_path", disabled=busy)
            st.caption("Use this fallback if a desktop folder chooser is unavailable.")
        status_slot = st.container()
        build_slot = st.container(key="build-slot")
        with st.expander("Index settings"):
            embedding_slot = st.container()
            refresh = st.button("Refresh models", disabled=busy)

    root = Path(root_text).expanduser().resolve() if root_text.strip() else None
    if str(root) != state.get("opened_root"):
        state.answer = None
        state.build_error = None
        state.action_error = None
        state.opened_root = str(root)
        if root:
            try:
                controller.open_repository(root)
            except RepoLensError:
                pass  # Report corruption in status while preserving the rebuild path.
        state.embedding_model = controller.settings.embedding_model

    if refresh or "models" not in state:
        try:
            state.models = controller.models()
            state.model_error = None
        except RepoLensError as exc:
            state.models = ()
            state.model_error = str(exc)
    models = state.get("models", ())
    answers = [model.name for model in models if "completion" in model.capabilities]
    embeddings = [model.name for model in models if "embedding" in model.capabilities]
    if "answer_model" not in state:
        state.answer_model = controller.settings.answer_model
    # Preserve missing preferences so users see a warning rather than substitution.
    answer_choices = list(dict.fromkeys([state.answer_model] + answers))
    embedding_choices = list(dict.fromkeys([state.embedding_model] + embeddings))
    with answer_panel:
        st.html('<div class="rl-eyebrow">02 / Retrieval & answers</div>')
        heading, model_control = st.columns([1.7, 1], gap="medium")
        with heading:
            st.subheader("Ask your repository", anchor=False)
            st.html(
                '<p class="rl-panel-description">Get an explanation you can check against the code.</p>'
            )
        with model_control:
            st.selectbox(
                "Answer model", answer_choices, key="answer_model", disabled=busy
            )
    with embedding_slot:
        st.selectbox(
            "Embedding model", embedding_choices, key="embedding_model", disabled=busy
        )
        st.caption(
            "Changing the embedding model requires a full rebuild. Answer models can change without rebuilding."
        )
        unsupported = [
            model.name
            for model in models
            if not model.capabilities & {"completion", "embedding"}
        ]
        if unsupported:
            st.caption("Unsupported capability metadata: " + ", ".join(unsupported))
    selection = (state.answer_model, state.embedding_model)
    if selection != (
        controller.settings.answer_model,
        controller.settings.embedding_model,
    ):
        state.answer = None
        try:
            controller.set_models(*selection)
        except RepoLensError as exc:
            answer_panel.error(str(exc))
            return
    answer_ready = state.answer_model in answers
    embedding_ready = state.embedding_model in embeddings
    with status_slot:
        if state.get("model_error"):
            st.error(state.model_error)
        if not embedding_ready:
            st.warning(
                "The embedding model is unavailable or unsupported. Start Ollama or select another compatible local model, then refresh models."
            )
        status = (
            controller.status(root)
            if root
            else IndexStatus("missing", None, "Select a repository folder.")
        )
        if status.state != "ready":
            state.answer = None
        _index_card(status, root)
        if state.get("build_error"):
            st.error(state.build_error)
    with build_slot:
        build_label = (
            "Retry rebuild"
            if state.get("build_error")
            else (
                "Rebuild index"
                if status.snapshot or status.state == "failed"
                else "Build index"
            )
        )
        st.button(
            build_label,
            key="build-action",
            type="primary",
            disabled=busy or root is None or not embedding_ready,
            on_click=queue,
            args=("build",),
        )
        st.caption("Rebuild explicitly when source files change.")
        st.caption(f"Local index storage: {controller.settings.data_dir}")
    with answer_panel:
        if not answer_ready:
            st.warning(
                "The answer model is unavailable or unsupported. Start Ollama or select another compatible local model, then refresh models."
            )
        question = st.text_area(
            "Question",
            key="question",
            disabled=busy,
            height=100,
            placeholder="Where is authentication checked?",
            max_chars=1000,
        )
        if question != state.get("answered_question"):
            state.answer = None
        st.caption("Each question is independent.")
        st.button(
            "Ask",
            type="primary",
            disabled=busy
            or status.state != "ready"
            or not answer_ready
            or not question.strip(),
            on_click=queue,
            args=("ask",),
        )
        if state.get("action_error"):
            st.error(state.action_error)
        if state.get("answer"):
            result = state.answer
            st.divider()
            st.subheader("Answer", anchor=False)
            # Keep model output plain text: no active HTML, images or remote links.
            st.text(result.answer)
            if result.insufficient_evidence:
                st.info(
                    "The retrieved evidence does not establish all requested information."
                )
            st.caption(
                f"{result.answer_model.name} · {result.timings['total_seconds']:.1f}s"
            )
            if result.sources:
                st.caption("Supporting sources · Original file line numbers")
            for source in result.sources:
                snippet = source.snippet
                with st.expander(
                    f"[{source.source_id}] {snippet.relative_path}:{snippet.start_line}–{snippet.end_line}"
                ):
                    st.code(
                        numbered_source(snippet), language="text", line_numbers=False
                    )
        elif not busy:
            _empty_answer(status, root)
    if busy:
        action = state.pending
        target = answer_panel if action == "ask" else repository_panel
        messages = {
            "browse": "Choose a folder in the system dialog…",
            "build": "Building index…",
            "ask": "Checking sources and answering…",
        }
        try:
            with target, st.spinner(messages[action]):
                if action == "browse":
                    state.folder_error = None
                    selected = choose_repository_folder(root)
                    if selected is not None:
                        state.chosen_root = str(selected)
                elif action == "build":
                    controller.build(root)
                    state.build_error = None
                else:
                    state.answer = controller.ask(root, question)
                    state.answered_question = question
        except RepoLensError as exc:
            if action == "browse":
                state.folder_error = str(exc)
            elif action == "build":
                state.build_error = str(exc)
            else:
                state.action_error = str(exc)
        finally:
            state.pending = None
        st.rerun()
    st.html(
        '<div class="rl-footer">Local files · Local models · Explicit rebuilds</div>'
    )
