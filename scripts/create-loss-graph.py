# SPDX-License-Identifier: Apache-2.0
# Standard
from argparse import ArgumentParser
from pathlib import Path
from subprocess import run
from typing import Dict, List
import json

# Third Party
from matplotlib import pyplot as plt
from pydantic import BaseModel


class Arguments(BaseModel):
    log_file: str | None = None
    output_file: str
    aws_region: str
    bucket_name: str
    base_branch: str
    pr_number: str
    head_sha: str
    origin_repository: str


def render_image(loss_data: List[float], outfile: Path) -> str:
    # create the plot
    plt.figure()
    plt.plot(loss_data)
    plt.xlabel("Steps")
    plt.ylabel("Loss")
    plt.title("Training performance over fixed dataset")

    if outfile.exists():
        outfile.unlink()

    plt.savefig(outfile, format="png")


def contents_from_file(log_file: Path) -> List[Dict]:
    if not log_file.exists():
        raise FileNotFoundError(f"Log file {log_file} does not exist")
    if log_file.is_dir():
        raise ValueError(f"Log file {log_file} is a directory")
    with open(log_file, "r") as f:
        return [json.loads(l) for l in f.read().splitlines()]


def read_loss_data(log_file: Path) -> List[float]:
    if not log_file:
        raise ValueError("log_file must be provided when source is file")
    contents = contents_from_file(log_file)

    # select the loss data
    loss_data = [item["total_loss"] for item in contents if "total_loss" in item]

    if not loss_data:
        raise ValueError("Loss data is empty")

    # ensure that the loss data is valid
    if not all(isinstance(l, float) for l in loss_data):
        raise ValueError("Loss data must be a list of floats")

    return loss_data


def write_to_s3(
    file: Path,
    bucket_name: str,
    destination: str,
):
    if not file.exists():
        raise RuntimeError(f"File {file} does not exist")

    s3_path = f"s3://{bucket_name}/{destination}"
    results = run(
        ["aws", "s3", "cp", str(file), s3_path], capture_output=True, check=True
    )
    if results.returncode != 0:
        raise RuntimeError(f"failed to upload to s3: {results.stderr.decode('utf-8')}")
    else:
        print(results.stdout.decode("utf-8"))


def get_destination_path(base_ref: str, pr_number: str, head_sha: str):
    return f"pulls/{base_ref}/{pr_number}/{head_sha}/loss-graph.png"


def write_md_file(
    output_file: Path, url: str, pr_number: str, head_sha: str, origin_repository: str
):
    commit_url = f"https://github.com/{origin_repository}/commit/{head_sha}"
    md_template = f"""
# Loss Graph for PR {args.pr_number} ([{args.head_sha[:7]}]({commit_url}))

![Loss Graph]({url})
"""
    output_file.write_text(md_template, encoding="utf-8")


def get_url(bucket_name: str, destination: str, aws_region: str) -> str:
    return f"https://{bucket_name}.s3.{aws_region}.amazonaws.com/{destination}"


def main(args: Arguments):
    # first things first, we create the png file to upload to S3
    log_file = Path(args.log_file)
    loss_data = read_loss_data(log_file=log_file)
    output_image = Path("/tmp/loss-graph.png")
    output_file = Path(args.output_file)
    render_image(loss_data=loss_data, outfile=output_image)
    destination_path = get_destination_path(
        base_ref=args.base_branch, pr_number=args.pr_number, head_sha=args.head_sha
    )
    write_to_s3(
        file=output_image, bucket_name=args.bucket_name, destination=destination_path
    )
    s3_url = get_url(
        bucket_name=args.bucket_name,
        destination=destination_path,
        aws_region=args.aws_region,
    )
    write_md_file(
        output_file=output_file,
        url=s3_url,
        pr_number=args.pr_number,
        head_sha=args.head_sha,
        origin_repository=args.origin_repository,
    )
    print(f"Loss graph uploaded to '{s3_url}'")
    print(f"Markdown file written to '{output_file}'")


if __name__ == "__main__":
    parser = ArgumentParser()

    parser.add_argument(
        "--log-file",
        type=str,
        required=True,
        help="The log file to read the loss data from.",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        required=True,
        help="The output file where the resulting markdown will be written.",
    )
    parser.add_argument(
        "--aws-region",
        type=str,
        required=True,
        help="S3 region to which the bucket belongs.",
    )
    parser.add_argument(
        "--bucket-name", type=str, required=True, help="The S3 bucket name"
    )
    parser.add_argument(
        "--base-branch",
        type=str,
        required=True,
        help="The base branch being merged to.",
    )
    parser.add_argument("--pr-number", type=str, required=True, help="The PR number")
    parser.add_argument(
        "--head-sha", type=str, required=True, help="The head SHA of the PR"
    )
    parser.add_argument(
        "--origin-repository",
        type=str,
        required=True,
        help="The repository to which the originating branch belongs to.",
    )

    args = parser.parse_args()

    arguments = Arguments(
        log_file=args.log_file,
        output_file=args.output_file,
        aws_region=args.aws_region,
        bucket_name=args.bucket_name,
        base_branch=args.base_branch,
        pr_number=args.pr_number,
        head_sha=args.head_sha,
        origin_repository=args.origin_repository,
    )
    main(arguments)