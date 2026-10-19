"""Reviewed, immutable execution boundary for the public Python-client case.

Graph traversal chooses applicable check IDs. This registry only translates IDs
to approved test commands; it does not establish a successful verification.
"""
import hashlib
import json

SCHEMA_VERSION = 1
REGISTRY_VERSION = "py211-v1"
POLICY_VERSION = "required-redis-800-810-v1"
CHANGE_ID = "FalkorDB/falkordb-py#212"
ISSUE_URL = "https://github.com/FalkorDB/falkordb-py/issues/211"
CHANGE_URL = "https://github.com/FalkorDB/falkordb-py/pull/212"
REPOSITORY = "FalkorDB/falkordb-py"
RUNNER_REPOSITORY = "RHUDHRESH/baton-graph-workspace"
WORKFLOW = "baton-verify.yml"
SOURCE_COMMIT = "207000da70ca183ab02990a98bdd97d0a3e3bb1b"
SOURCE_ARCHIVE_SHA256 = "cb2057288440cfc977da4bcfbf3770a3a577511f6ef5d3b5b79cf4006ea1a499"
FALKORDB_IMAGE = "falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a"
PYTHON_VERSION = "3.13.5"
PYTHON_IMAGE = "python@sha256:a7cb177dc60dfa77b223192cd0d9e6ce1aac7cf9a569023d68e7c91b6371a718"
CHECK_IDS = (
    "tests/test_graph.py::test_param_non_identifier_keys",
    "tests/test_graph.py::test_param_invalid_keys_rejected",
    "tests/test_async_graph.py::test_param_non_identifier_keys",
    "tests/test_async_graph.py::test_param_invalid_keys_rejected",
)
CHECKS = {identity: {"id": identity, "surface": "async" if "test_async_graph" in identity else "sync",
                    "label": identity.rsplit("::", 1)[1]} for identity in CHECK_IDS}
ENVIRONMENTS = (
    {"id": "redis-8.0.0", "redis_version": "8.0.0", "required": True},
    {"id": "redis-8.1.0", "redis_version": "8.1.0", "required": True},
)
DEPENDENCIES = {
    "coverage": "7.16.2", "iniconfig": "2.3.1", "packaging": "26.3",
    "pluggy": "1.7.0", "Pygments": "2.21.0", "pytest": "9.1.1",
    "pytest-asyncio": "1.4.0", "pytest-cov": "7.1.0",
    "python-dateutil": "2.9.0.post0", "six": "1.17.0",
}
SOURCE_HASHES = {
    "falkordb/graph.py": "a14f09fb7322d3e7e2e808d97f4103e460a62c39212d9fb76769223227e85036",
    "falkordb/helpers.py": "a97d54c480b98e550af3b2dfd324e82669266ddf07547e9fedc5aaf50285c6a1",
    "falkordb/asyncio/graph.py": "41fc523886a2b40e2874dfba13387306ef853cfe098b0a54683722b66fb47f0f",
    "tests/test_graph.py": "f9f4be99d4887cd4f1c989fe3f145eb74d05a8deae583b2209cd192522cf3197",
    "tests/test_async_graph.py": "8d59ac14963d1e8131ada191292ee2f241da933645d3feed9fa9dfcd12b8eecc",
}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def selected_ids(plan):
    return [row["id"] if isinstance(row, dict) else row for row in plan.get("required_checks", [])]


PLAN_BINDING_FIELDS = (
    "schema_version", "registry_version", "policy_version", "change_id", "title",
    "source_commit", "source_archive_sha256", "source_hashes", "python_image",
    "python_version", "falkordb_image", "graph", "plan_status", "required_checks",
    "environments", "source_versions", "witness_paths", "binding_fingerprint",
)


def plan_hash(plan):
    """Exclude UI metadata, model prose and unrelated graph revisions."""
    return sha(encode({key: plan.get(key) for key in PLAN_BINDING_FIELDS}))
