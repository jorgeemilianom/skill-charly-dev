#!/usr/bin/env python3
"""Strip the noise every raw Jira API response carries — null fields, `self` links, avatar URL
sets, `expand`/`schema` metadata — none of it useful to an agent reading the ticket, all of it
tokens. Generic: doesn't know or care about specific field names, so it doesn't need updating
when custom fields change. Verified against real MSOF tickets: ~30-40% smaller, same information.

Usage: uv run <jira-communication>/core/jira-issue.py --json get <KEY> | python3 scripts/jira_trim.py
       uv run <jira-communication>/utility/jira-qa-gather.py --json <KEY> | python3 scripts/jira_trim.py
"""
import json
import sys

DROP_KEYS = {'self', 'avatarUrls', 'expand', 'schema'}


def prune(obj):
    if isinstance(obj, dict):
        return {
            k: prune(v) for k, v in obj.items()
            if v not in (None, [], {}) and k not in DROP_KEYS
        }
    if isinstance(obj, list):
        return [prune(x) for x in obj]
    return obj


def main():
    data = json.load(sys.stdin)
    data.pop('renderedFields', None)  # HTML-rendered duplicate of `fields` — qa-gather only
    if isinstance(data, dict) and 'issue' in data and isinstance(data['issue'], dict):
        data['issue'].pop('renderedFields', None)
    print(json.dumps(prune(data), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
