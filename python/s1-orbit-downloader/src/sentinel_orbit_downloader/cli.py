from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from sentinel_orbit_downloader.core.config import DEFAULT_DB_PATH
from sentinel_orbit_downloader.services.aoi import aoi_file_to_wkt, bbox_to_wkt
from sentinel_orbit_downloader.services.asf_client import (
    SearchParams,
    product_size_mb,
    query_scenes,
    scene_name_from_product,
    write_manifest,
)
from sentinel_orbit_downloader.services.orbit_client import (
    collect_orbit_scenes,
    download_orbits,
)
from sentinel_orbit_downloader.services.download_manager import (
    DownloadJobRequest,
    execute_download_job,
    queue_download_job,
)
from sentinel_orbit_downloader.services.project_store import (
    create_project,
    create_search_job,
    get_job,
    get_project,
    list_job_events,
    list_job_scenes,
    list_jobs,
    list_projects,
    record_download_result,
    record_job_event,
    save_query_results,
    update_search_job,
)
from sentinel_orbit_downloader.services.region_catalog import (
    get_region,
    import_regions,
    region_wkt,
    search_regions,
)


DEFAULT_REGION_FILE = Path("\u5168\u56fd\u884c\u653f\u533a.geojson")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s1-dl",
        description="Query and download Sentinel-1 scenes plus matching orbit files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="query Sentinel-1 scenes")
    add_database_arg(search_parser)
    add_project_arg(search_parser)
    add_query_args(search_parser)
    add_manifest_arg(search_parser)
    search_parser.set_defaults(func=cmd_search)

    download_parser = subparsers.add_parser(
        "download",
        help="query scenes, download products, and fetch matching orbit files",
    )
    add_database_arg(download_parser)
    add_project_arg(download_parser)
    add_query_args(download_parser)
    download_parser.add_argument(
        "--out",
        type=Path,
        default=Path("downloads"),
        help="output root directory; data and orbits subdirectories are created here",
    )
    download_parser.add_argument(
        "--data-dir",
        type=Path,
        help="override product download directory; default is <out>/data",
    )
    download_parser.add_argument(
        "--orbit-dir",
        type=Path,
        help="override orbit download directory; default is <out>/orbits",
    )
    download_parser.add_argument(
        "--username",
        help="NASA Earthdata username; defaults to EARTHDATA_USER or EARTHDATA_USERNAME",
    )
    download_parser.add_argument(
        "--password",
        help="NASA Earthdata password; defaults to EARTHDATA_PASS or EARTHDATA_PASSWORD",
    )
    download_parser.add_argument(
        "--ask-password",
        action="store_true",
        help="prompt for the Earthdata password instead of reading an argument/env var",
    )
    download_parser.add_argument(
        "--processes",
        type=positive_int,
        default=3,
        help="retry attempts for each product download",
    )
    download_parser.add_argument(
        "--skip-data",
        action="store_true",
        help="do not download product zip files; useful for orbit-only runs from query results",
    )
    download_parser.add_argument(
        "--skip-orbits",
        action="store_true",
        help="do not download matching orbit files",
    )
    download_parser.add_argument(
        "--ignore-orbit-errors",
        action="store_true",
        help="return success even if some orbit files cannot be found",
    )
    add_manifest_arg(download_parser)
    download_parser.set_defaults(func=cmd_download)

    orbit_parser = subparsers.add_parser(
        "orbits",
        help="download orbit files for existing scenes or local .zip/.SAFE products",
    )
    scene_group = orbit_parser.add_mutually_exclusive_group(required=True)
    scene_group.add_argument(
        "--scene",
        action="append",
        help="Sentinel-1 scene name; may be repeated",
    )
    scene_group.add_argument(
        "--scene-file",
        type=Path,
        help="text file containing one scene name per line",
    )
    scene_group.add_argument(
        "--data-dir",
        type=Path,
        help="directory containing Sentinel-1 .zip files or .SAFE folders",
    )
    orbit_parser.add_argument(
        "--out",
        type=Path,
        default=Path("orbits"),
        help="orbit output directory",
    )
    orbit_parser.add_argument(
        "--ignore-errors",
        action="store_true",
        help="return success even if some orbit files cannot be found",
    )
    orbit_parser.set_defaults(func=cmd_orbits)

    regions_parser = subparsers.add_parser(
        "regions",
        help="import and query administrative boundary regions",
    )
    add_database_arg(regions_parser)
    region_subparsers = regions_parser.add_subparsers(dest="regions_command", required=True)

    regions_import = region_subparsers.add_parser("import", help="import a GeoJSON region catalog")
    add_database_arg(regions_import)
    regions_import.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_REGION_FILE,
        help=f"GeoJSON source file; default is .\\{DEFAULT_REGION_FILE.name}",
    )
    regions_import.add_argument(
        "--simplify-tolerance",
        type=float,
        default=0.01,
        help="Shapely simplify tolerance used to derive query WKT",
    )
    regions_import.set_defaults(func=cmd_regions_import)

    regions_search_parser = region_subparsers.add_parser("search", help="search regions by name or adcode")
    add_database_arg(regions_search_parser)
    regions_search_parser.add_argument("query", help="query text, for example mudanjiang or 231000")
    regions_search_parser.add_argument(
        "--limit",
        type=positive_int,
        default=20,
        help="maximum number of matches to return",
    )
    regions_search_parser.add_argument(
        "--level",
        choices=("country", "province", "city", "district"),
        help="optional level filter",
    )
    regions_search_parser.set_defaults(func=cmd_regions_search)

    regions_export_parser = region_subparsers.add_parser("export", help="export region geometry or metadata")
    add_database_arg(regions_export_parser)
    regions_export_parser.add_argument("adcode", help="region adcode")
    regions_export_parser.add_argument(
        "--format",
        choices=("wkt", "geojson", "bbox", "json"),
        default="wkt",
        help="output format",
    )
    regions_export_parser.add_argument(
        "--raw",
        action="store_true",
        help="use the original geometry instead of simplified WKT/json",
    )
    regions_export_parser.add_argument(
        "--out",
        type=Path,
        help="optional file to write the exported value to",
    )
    regions_export_parser.set_defaults(func=cmd_regions_export)

    projects_parser = subparsers.add_parser("projects", help="manage local projects")
    add_database_arg(projects_parser)
    project_subparsers = projects_parser.add_subparsers(dest="projects_command", required=True)

    projects_create = project_subparsers.add_parser("create", help="create a project")
    add_database_arg(projects_create)
    projects_create.add_argument("--name", required=True, help="project name")
    projects_create.add_argument("--data-root", type=Path, required=True, help="project data root")
    projects_create.add_argument("--description", help="optional description")
    projects_create.add_argument("--slug", help="optional directory-friendly slug")
    projects_create.set_defaults(func=cmd_projects_create)

    projects_list_parser = project_subparsers.add_parser("list", help="list projects")
    add_database_arg(projects_list_parser)
    projects_list_parser.set_defaults(func=cmd_projects_list)

    projects_show_parser = project_subparsers.add_parser("show", help="show one project")
    add_database_arg(projects_show_parser)
    projects_show_parser.add_argument("project_id", type=positive_int, help="project id")
    projects_show_parser.set_defaults(func=cmd_projects_show)

    jobs_parser = subparsers.add_parser("jobs", help="inspect saved query and download jobs")
    add_database_arg(jobs_parser)
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command", required=True)

    jobs_list_parser = jobs_subparsers.add_parser("list", help="list recent jobs")
    add_database_arg(jobs_list_parser)
    jobs_list_parser.add_argument("--project-id", type=positive_int, help="optional project filter")
    jobs_list_parser.add_argument("--limit", type=positive_int, default=20, help="maximum jobs to list")
    jobs_list_parser.set_defaults(func=cmd_jobs_list)

    jobs_show_parser = jobs_subparsers.add_parser("show", help="show one job and its scenes")
    add_database_arg(jobs_show_parser)
    jobs_show_parser.add_argument("job_id", type=positive_int, help="job id")
    jobs_show_parser.add_argument(
        "--events",
        action="store_true",
        help="include stored job events",
    )
    jobs_show_parser.set_defaults(func=cmd_jobs_show)

    return parser


def add_database_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path; default is {DEFAULT_DB_PATH}",
    )


def add_project_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-id",
        type=positive_int,
        help="optional project id used to group saved jobs",
    )


def add_query_args(parser: argparse.ArgumentParser) -> None:
    aoi = parser.add_mutually_exclusive_group(required=True)
    aoi.add_argument("--bbox", help="AOI bounding box as min_lon,min_lat,max_lon,max_lat")
    aoi.add_argument("--wkt", help="AOI as WKT, for example POLYGON((...))")
    aoi.add_argument(
        "--aoi-file",
        type=Path,
        help="AOI file containing WKT, GeoJSON Feature, or GeoJSON geometry",
    )
    aoi.add_argument(
        "--region-adcode",
        help="AOI from imported region catalog; use `s1-dl regions search` first",
    )
    parser.add_argument(
        "--raw-region",
        action="store_true",
        help="when using --region-adcode, use the original geometry instead of simplified WKT",
    )
    parser.add_argument("--start", required=True, help="start date/time, e.g. 2024-01-01")
    parser.add_argument("--end", required=True, help="end date/time, e.g. 2024-02-01")
    parser.add_argument(
        "--processing-level",
        default="SLC",
        help="ASF processing level, e.g. SLC, GRD_HD, GRD_MD, OCN",
    )
    parser.add_argument("--beam-mode", default="IW", help="beam mode, e.g. IW, EW, WV")
    parser.add_argument(
        "--flight-direction",
        choices=("ASCENDING", "DESCENDING", "ascending", "descending"),
        help="optional orbit direction filter",
    )
    parser.add_argument("--polarization", help="optional polarization filter, e.g. VV+VH")
    parser.add_argument(
        "--relative-orbit",
        type=positive_int,
        help="optional Sentinel-1 relative orbit/track number",
    )
    parser.add_argument(
        "--max-results",
        type=positive_int,
        default=50,
        help="maximum scenes to return",
    )


def add_manifest_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, help="write search results to .csv or .json")


def cmd_search(args: argparse.Namespace) -> int:
    ensure_project_exists(args.db, args.project_id)
    aoi_meta = resolve_aoi(args)
    job = create_search_job(
        args.db,
        project_id=args.project_id,
        source_type=aoi_meta["source_type"],
        source_value=aoi_meta["source_value"],
        region_adcode=aoi_meta["region_adcode"],
        region_name=aoi_meta["region_name"],
        start_time=args.start,
        end_time=args.end,
        processing_level=args.processing_level,
        beam_mode=args.beam_mode,
        flight_direction=args.flight_direction.upper() if args.flight_direction else None,
        polarization=args.polarization,
        relative_orbit=args.relative_orbit,
        max_results=args.max_results,
        manifest_path=str(args.manifest) if args.manifest else None,
    )
    record_job_event(args.db, job.id, "info", "Query created")

    try:
        results = perform_query(args, aoi_meta["aoi_wkt"])
        save_query_results(args.db, job.id, results)
        print_results(results)
        if args.manifest:
            write_manifest(results, args.manifest)
            print(f"Wrote manifest: {args.manifest}")
        update_search_job(
            args.db,
            job.id,
            status="succeeded",
            result_count=len(results),
            manifest_path=str(args.manifest) if args.manifest else None,
        )
        record_job_event(args.db, job.id, "info", f"Query returned {len(results)} scene(s)")
    except Exception as exc:
        update_search_job(args.db, job.id, status="failed", error_message=str(exc))
        record_job_event(args.db, job.id, "error", f"Query failed: {exc}")
        raise

    print(f"Saved job: {job.id}")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    ensure_project_exists(args.db, args.project_id)
    aoi_meta = resolve_aoi(args)

    out_root = args.out
    data_dir = args.data_dir or out_root / "data"
    orbit_dir = args.orbit_dir or out_root / "orbits"
    out_root.mkdir(parents=True, exist_ok=True)
    manifest = args.manifest or out_root / "manifest.csv"

    job = create_search_job(
        args.db,
        project_id=args.project_id,
        source_type=aoi_meta["source_type"],
        source_value=aoi_meta["source_value"],
        region_adcode=aoi_meta["region_adcode"],
        region_name=aoi_meta["region_name"],
        start_time=args.start,
        end_time=args.end,
        processing_level=args.processing_level,
        beam_mode=args.beam_mode,
        flight_direction=args.flight_direction.upper() if args.flight_direction else None,
        polarization=args.polarization,
        relative_orbit=args.relative_orbit,
        max_results=args.max_results,
        data_dir=str(data_dir),
        orbit_dir=str(orbit_dir),
        manifest_path=str(manifest),
    )
    record_job_event(args.db, job.id, "info", "Download job created")

    try:
        results = perform_query(args, aoi_meta["aoi_wkt"])
        save_query_results(args.db, job.id, results)
        record_job_event(args.db, job.id, "info", f"Query returned {len(results)} scene(s)")
        update_search_job(
            args.db,
            job.id,
            status="running",
            result_count=len(results),
            data_dir=str(data_dir),
            orbit_dir=str(orbit_dir),
            manifest_path=str(manifest),
        )

        print_results(results)
        write_manifest(results, manifest)
        print(f"Wrote manifest: {manifest}")

        if not results:
            update_search_job(
                args.db,
                job.id,
                status="succeeded",
                result_count=0,
                data_dir=str(data_dir),
                orbit_dir=str(orbit_dir),
                manifest_path=str(manifest),
            )
            record_job_event(args.db, job.id, "info", "No scenes matched the query")
            print(f"Saved job: {job.id}")
            return 0

        password = args.password
        if args.ask_password and not args.skip_data:
            password = getpass.getpass("Earthdata password: ")

        manager_request = DownloadJobRequest(
            job_id=job.id,
            data_dir=data_dir,
            orbit_dir=orbit_dir,
            manifest_path=manifest,
            skip_data=args.skip_data,
            skip_orbits=args.skip_orbits,
            processes=args.processes,
            ignore_orbit_errors=args.ignore_orbit_errors,
            username=args.username,
            password=password,
        )
        queue_download_job(args.db, manager_request)
        print(f"Downloading {len(results)} scene(s) with resume and validation support ...")
        execute_download_job(args.db, manager_request)

        finished_job = get_job(args.db, job.id)
        final_status = finished_job.status if finished_job is not None else "failed"
        print(f"Download job finished: {final_status}")
        print(f"Saved job: {job.id}")
        if final_status in {"failed", "partial_failed"}:
            return 1
        return 0
    except Exception as exc:
        update_search_job(
            args.db,
            job.id,
            status="failed",
            result_count=None,
            data_dir=str(data_dir),
            orbit_dir=str(orbit_dir),
            manifest_path=str(manifest),
            error_message=str(exc),
        )
        record_job_event(args.db, job.id, "error", f"Download job failed: {exc}")
        raise


def cmd_orbits(args: argparse.Namespace) -> int:
    scenes = collect_orbit_scenes(
        scenes=args.scene,
        scene_file=args.scene_file,
        data_dir=args.data_dir,
    )
    if not scenes:
        print("No Sentinel-1 scenes found.", file=sys.stderr)
        return 1

    print(f"Downloading orbit files for {len(scenes)} scene(s) to {args.out} ...")
    results = download_orbits(scenes, args.out)
    failures = summarize_orbit_results(results)
    if failures and not args.ignore_errors:
        return 1
    return 0


def cmd_regions_import(args: argparse.Namespace) -> int:
    if not args.source.exists():
        raise ValueError(f"GeoJSON file does not exist: {args.source}")
    stats = import_regions(args.db, args.source, simplify_tolerance=args.simplify_tolerance)
    print(
        "Imported region catalog: "
        f"{stats.imported}/{stats.total_features} features "
        f"from {stats.source_path} with simplify_tolerance={stats.simplify_tolerance}"
    )
    return 0


def cmd_regions_search(args: argparse.Namespace) -> int:
    matches = search_regions(args.db, args.query, limit=args.limit, level=args.level)
    if not matches:
        print("No regions matched.")
        return 0

    for region in matches:
        bbox_text = ""
        if region.bbox is not None:
            bbox_text = ",".join(f"{value:.6f}" for value in region.bbox)
        print(f"{region.adcode} | {region.level:<8} | {region.label} | {bbox_text}")
    return 0


def cmd_regions_export(args: argparse.Namespace) -> int:
    region = get_region(args.db, args.adcode)
    if region is None:
        raise ValueError(f"region not found: {args.adcode}")

    if args.format == "wkt":
        output = region.wkt if args.raw else region.simplified_wkt
    elif args.format == "geojson":
        output = region.geometry_json
    elif args.format == "bbox":
        if region.bbox is None:
            raise ValueError(f"region has no bbox: {args.adcode}")
        output = ",".join(str(value) for value in region.bbox)
    else:
        payload: dict[str, Any] = {
            "adcode": region.adcode,
            "name": region.name,
            "level": region.level,
            "parent_adcode": region.parent_adcode,
            "parent_name": region.parent_name,
            "province_adcode": region.province_adcode,
            "province_name": region.province_name,
            "bbox": region.bbox,
            "simplify_tolerance": region.simplify_tolerance,
            "label": region.label,
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(f"Wrote region export: {args.out}")
    else:
        print(output)
    return 0


def cmd_projects_create(args: argparse.Namespace) -> int:
    project = create_project(
        args.db,
        name=args.name,
        data_root=args.data_root,
        description=args.description,
        slug=args.slug,
    )
    print(f"Created project: {project.id} | {project.slug} | {project.data_root}")
    return 0


def cmd_projects_list(args: argparse.Namespace) -> int:
    projects = list_projects(args.db)
    if not projects:
        print("No projects found.")
        return 0
    for project in projects:
        desc = f" | {project.description}" if project.description else ""
        print(f"{project.id} | {project.slug} | {project.name} | {project.data_root}{desc}")
    return 0


def cmd_projects_show(args: argparse.Namespace) -> int:
    project = get_project(args.db, args.project_id)
    if project is None:
        raise ValueError(f"project not found: {args.project_id}")
    print(json.dumps(project.__dict__, ensure_ascii=False, indent=2))
    return 0


def cmd_jobs_list(args: argparse.Namespace) -> int:
    jobs = list_jobs(args.db, project_id=args.project_id, limit=args.limit)
    if not jobs:
        print("No jobs found.")
        return 0
    for job in jobs:
        project_text = job.project_id if job.project_id is not None else "-"
        target = job.region_name or job.source_value or job.source_type
        print(
            f"{job.id} | project={project_text} | {job.status:<14} | "
            f"{job.start_time}..{job.end_time} | {target} | count={job.result_count}"
        )
    return 0


def cmd_jobs_show(args: argparse.Namespace) -> int:
    job = get_job(args.db, args.job_id)
    if job is None:
        raise ValueError(f"job not found: {args.job_id}")

    print(json.dumps(job.__dict__, ensure_ascii=False, indent=2))
    scenes = list_job_scenes(args.db, args.job_id)
    if scenes:
        print("\nScenes:")
        for scene in scenes:
            size_text = f"{scene['size_mb']:.1f} MB" if scene["size_mb"] is not None else ""
            print(
                f"  {scene['scene_id']} | {scene['start_time']} | {scene['processing_level']} | "
                f"product={scene['product_status']} | orbit={scene['orbit_status']} | {size_text}"
            )
    if args.events:
        events = list_job_events(args.db, args.job_id)
        if events:
            print("\nEvents:")
            for event in events:
                print(f"  [{event['created_at']}] {event['level']}: {event['message']}")
    return 0


def perform_query(args: argparse.Namespace, aoi_wkt: str):
    params = SearchParams(
        aoi_wkt=aoi_wkt,
        start=args.start,
        end=args.end,
        processing_level=args.processing_level,
        beam_mode=args.beam_mode,
        flight_direction=args.flight_direction,
        polarization=args.polarization,
        relative_orbit=args.relative_orbit,
        max_results=args.max_results,
    )
    print("Querying ASF Search ...")
    return query_scenes(params)


def resolve_aoi(args: argparse.Namespace) -> dict[str, Any]:
    if args.bbox:
        return {
            "aoi_wkt": bbox_to_wkt(args.bbox),
            "source_type": "bbox",
            "source_value": args.bbox,
            "region_adcode": None,
            "region_name": None,
        }
    if args.wkt:
        return {
            "aoi_wkt": args.wkt.strip(),
            "source_type": "wkt",
            "source_value": args.wkt.strip(),
            "region_adcode": None,
            "region_name": None,
        }
    if args.aoi_file:
        return {
            "aoi_wkt": aoi_file_to_wkt(args.aoi_file),
            "source_type": "aoi_file",
            "source_value": str(args.aoi_file),
            "region_adcode": None,
            "region_name": None,
        }
    if args.region_adcode:
        region = get_region(args.db, args.region_adcode)
        if region is None:
            raise ValueError(f"region not found: {args.region_adcode}")
        return {
            "aoi_wkt": region_wkt(args.db, args.region_adcode, simplified=not args.raw_region),
            "source_type": "region",
            "source_value": region.label,
            "region_adcode": region.adcode,
            "region_name": region.label,
        }
    raise ValueError("one AOI input is required")


def print_results(results) -> None:
    count = len(results)
    print(f"Found {count} scene(s).")
    if not count:
        return

    for index, product in enumerate(results, start=1):
        props = product.properties
        scene = scene_name_from_product(product) or props.get("fileID") or "<unknown>"
        start = props.get("startTime") or ""
        level = props.get("processingLevel") or ""
        direction = props.get("flightDirection") or ""
        rel_orbit = props.get("pathNumber") or ""
        size = product_size_mb(props)
        size_text = f"{size:.1f} MB" if size is not None else ""
        print(f"{index:>3}. {scene} | {start} | {level} | {direction} | rel={rel_orbit} | {size_text}")


def record_product_downloads(db_path: Path, job_id: int, results, data_dir: Path | None) -> None:
    for product in results:
        scene_id = scene_name_from_product(product)
        if scene_id is None:
            continue
        props = product.properties
        if data_dir is None:
            record_download_result(
                db_path,
                job_id=job_id,
                scene_id=scene_id,
                kind="product",
                status="skipped",
                path=None,
                url=string_value(props.get("url")),
                bytes_total=float(props["bytes"]) if props.get("bytes") is not None else None,
                bytes_done=0,
            )
            continue

        expected = expected_product_path(product, data_dir)
        status = "succeeded" if expected.exists() else "failed"
        record_download_result(
            db_path,
            job_id=job_id,
            scene_id=scene_id,
            kind="product",
            status=status,
            path=str(expected) if expected.exists() else None,
            url=string_value(props.get("url")),
            bytes_total=float(props["bytes"]) if props.get("bytes") is not None else None,
            bytes_done=float(props["bytes"]) if expected.exists() and props.get("bytes") is not None else None,
            error_message=None if expected.exists() else "Downloaded file not found at expected path",
        )


def record_orbit_downloads(db_path: Path, job_id: int, orbit_results) -> None:
    for result in orbit_results:
        record_download_result(
            db_path,
            job_id=job_id,
            scene_id=result.scene,
            kind="orbit",
            status="succeeded" if result.error is None else "failed",
            path=str(result.path) if result.path is not None else None,
            error_message=result.error,
        )


def expected_product_path(product, data_dir: Path) -> Path:
    props = product.properties
    file_name = props.get("fileName")
    if file_name:
        return data_dir / str(file_name)
    url = props.get("url")
    if url:
        return data_dir / Path(str(url)).name
    scene = scene_name_from_product(product) or "unknown_scene"
    return data_dir / f"{scene}.zip"


def summarize_orbit_results(results) -> int:
    failures = [result for result in results if result.error]
    for result in results:
        if result.error:
            print(f"Orbit failed: {result.scene}: {result.error}", file=sys.stderr)
        else:
            print(f"Orbit: {result.scene} -> {result.path.name}")
    print(f"Orbit download finished: {len(results) - len(failures)} ok, {len(failures)} failed.")
    return len(failures)


def ensure_project_exists(db_path: Path, project_id: int | None) -> None:
    if project_id is None:
        return
    if get_project(db_path, project_id) is None:
        raise ValueError(f"project not found: {project_id}")


def string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return number
