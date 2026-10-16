"""Favro REST API workflow for Mistral managed deployments."""

import asyncio

try:
    import mistralai_workflows
except ImportError:  # namespace-package layout
    from mistralai import workflows as mistralai_workflows

from src.workflows.favro import FavroRequestWorkflow


async def main() -> None:
    await mistralai_workflows.run_worker([FavroRequestWorkflow])


if __name__ == "__main__":
    asyncio.run(main())
