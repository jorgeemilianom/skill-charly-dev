#!/usr/bin/env bash
# Sourced once $WS is already known (source "$WS/scripts/workspace-env.sh") — loads config.sh
# and sets the derived vars most skill steps need. Safe to source even when a given step only
# needs one of the derived vars; both are cheap to compute.
source "$WS/config.sh"
JIRA_SKILL="${JIRA_SCRIPTS:-$WS/scripts/jira-communication/scripts}"
PROJECTS_PREFIX="${PROJECTS_SUBDIR:+$PROJECTS_SUBDIR/}"
