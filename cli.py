"""DriveScope CLI:  python -m drivescope.cli analyze FILE [-o report.html] [--json out.json] [--channels map.json]"""
import argparse, json, sys
from .engine import analyze
from .report import write_report


def main(argv=None):
    p = argparse.ArgumentParser(prog="drivescope", description="Diagnose drivability events from an MDF/.dat recording.")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyze a recording")
    a.add_argument("file", help="path to .dat / .mf4 recording")
    a.add_argument("-o", "--out", default=None, help="output HTML report path (default <file>.report.html)")
    a.add_argument("--json", default=None, help="also write the raw result JSON here")
    a.add_argument("--channels", default=None, help="custom channel-map JSON")
    a.add_argument("--max-events", type=int, default=12)
    args = p.parse_args(argv)

    if args.cmd == "analyze":
        print(f"[drivescope] parsing {args.file} …", file=sys.stderr)
        res = analyze(args.file, channel_config=args.channels, max_events=args.max_events)
        print(f"[drivescope] {res['n_events']} event(s); "
              f"{len(res['channels_resolved'])} channels resolved, "
              f"{len(res['channels_unresolved'])} unresolved.", file=sys.stderr)
        out = args.out or (args.file + ".report.html")
        write_report(res, out)
        print(f"[drivescope] report -> {out}", file=sys.stderr)
        if args.json:
            json.dump(res, open(args.json, "w"))
            print(f"[drivescope] json   -> {args.json}", file=sys.stderr)
        # concise stdout summary
        for e in res["events"]:
            m = e["metrics"]
            print(f"  {e['label']:34} [{e['verdict'].upper():4}] "
                  f"resp={m.get('tot_ms')}ms exec={m.get('exec_ms')}ms "
                  f"+g={m.get('posg')} fs={m.get('fs')}Hz")


if __name__ == "__main__":
    main()
