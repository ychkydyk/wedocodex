"""Compatibility entry point; implementation ships inside the portable skill."""
from skill.scripts.wedocodex import *

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f'WEDOCODEX: {exc}', file=sys.stderr)
        raise SystemExit(1)
