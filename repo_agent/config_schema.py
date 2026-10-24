"""Closed configuration schema mirroring PRD §4 (C4: the spec lives here,
not inline in the validator). Types:

- "str", "int", "bool" — scalars (bool is not an int here)
- "str_list" — nonempty list of nonempty strings
- "argv" — nonempty list of nonempty strings (a command line)
- "path" / "path_list" — repo-relative safe paths (checked by config.py)
- "glob_list" — glob patterns with the same path-safety rules
- "verify" — list of command names (resolved + cycle-checked by config.py)
- "enum:<v1>|<v2>" — one of the named values

Everything a project may configure is listed; anything else is an
unknown_field rejection.
"""

SCHEMA_VERSION = 1
MAX_BYTES = 262144
MAX_DEPTH = 5

STRING = "str"
INT = "int"
BOOL = "bool"

SECTIONS: dict[str, dict[str, object]] = {
    "project": {
        "name": STRING,
        "maturity": "enum:new|mature",
        "architecture": "path",
    },
    "environment": {
        "setup": "argv",
        "required_tools": "str_list",
    },
    "commands": {"*": "argv", "verify": "verify"},
    "instructions": {
        "policy_version": STRING,
        "project_notes": "path",
        "scoped": "path_list",
    },
    "boundaries": {
        "generated": "glob_list",
        "sensitive": "glob_list",
        "preserve": "str_list",
    },
    "skills": {
        "required": "str_list",
        "conditional": "str_list",
        "lock_file": "path",
    },
    "execution": {
        "adapter": "enum:dsh",
        "profile": STRING,
        "sandbox_profile": STRING,
        "max_attempts": INT,
        "max_attempts_without_new_evidence": INT,
        "timeout_seconds": INT,
    },
    "routing": {
        "default": "enum:local|frontier",
        "frontier_when": "str_list",
    },
    "evaluation": {
        "suite": STRING,
        "verifier_profile": STRING,
    },
    "learning": {
        "capture": BOOL,
        "propose_lessons": BOOL,
        "auto_promote": BOOL,
    },
    "memory": {
        "schema_version": INT,
        "canonical_owner": STRING,
        "default_scope": STRING,
        "cross_project": STRING,
        "writer": {
            "backend": STRING,
            "schedule": STRING,
            "debounce_seconds": INT,
            "max_pending_batches": INT,
        },
        "retrieval": {
            "initial_backend": STRING,
            "context_budget_tokens": INT,
            "triggers": "str_list",
        },
        "promotion": {
            "facts": STRING,
            "procedures": STRING,
            "reusable_rules": STRING,
        },
        "model_specific_default": STRING,
    },
    "model_switch": {
        "require_checkpoint": BOOL,
        "require_qualification": BOOL,
        "transfer_inference_cache": BOOL,
        "rollback_profile": STRING,
    },
    "context_management": {
        "mode": "enum:off|observe_only|validated_edits",
        "editable_regions": "str_list",
        "triggers": "str_list",
        "max_edit_attempts_per_checkpoint": INT,
        "archive_before_edit": BOOL,
        "require_revision_match": BOOL,
        "reserve_output_tokens": INT,
        "engine_reuse": STRING,
        "recompute_fallback": BOOL,
        "approximate_suffix_reuse": BOOL,
        "rendering": STRING,
    },
    "design": {
        "mode": "enum:auto_when_relevant|off|required",
        "preference_questions": STRING,
        "preserve_existing_system": BOOL,
        "planning": {
            "backend_only": STRING,
            "routine_ui_change": STRING,
            "new_interface": STRING,
            "substantial_redesign": STRING,
        },
        "references": {
            "max_per_decision": INT,
            "verify_before_use": BOOL,
            "auto_install": BOOL,
        },
        "skills": {"router": STRING, "optional_candidates": "str_list"},
        "review": {
            "rendered_ui": STRING,
            "responsive": STRING,
            "interaction_states": STRING,
            "keyboard_and_focus": STRING,
            "reduced_motion": STRING,
        },
    },
}

REQUIRED_SECTIONS = ("schema_version", "project", "commands")

DEFAULTS: dict[str, object] = {
    "execution.adapter": "dsh",
    "execution.max_attempts": 3,
    "execution.max_attempts_without_new_evidence": 2,
    "execution.timeout_seconds": 1800,
    "learning.capture": True,
    "learning.propose_lessons": True,
    "learning.auto_promote": False,
    "memory.schema_version": 1,
    "memory.default_scope": "repository",
    "memory.cross_project": "reviewed_export_only",
    "memory.retrieval.context_budget_tokens": 1500,
    "context_management.mode": "observe_only",
    "context_management.archive_before_edit": True,
    "context_management.require_revision_match": True,
    "context_management.max_edit_attempts_per_checkpoint": 1,
    "context_management.approximate_suffix_reuse": False,
    "context_management.recompute_fallback": True,
    "context_management.rendering": "markdown",
    "design.mode": "auto_when_relevant",
    "design.preserve_existing_system": True,
    "design.references.max_per_decision": 3,
    "design.references.verify_before_use": True,
    "design.references.auto_install": False,
}

POSITIVE_INTS = {
    "execution.max_attempts",
    "execution.max_attempts_without_new_evidence",
    "execution.timeout_seconds",
    "memory.writer.debounce_seconds",
    "memory.writer.max_pending_batches",
    "memory.retrieval.context_budget_tokens",
    "context_management.max_edit_attempts_per_checkpoint",
    "context_management.reserve_output_tokens",
    "design.references.max_per_decision",
}
