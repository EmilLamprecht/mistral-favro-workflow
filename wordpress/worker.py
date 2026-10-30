"""WordPress REST API workflow for Mistral managed deployments."""

import asyncio

try:
    import mistralai_workflows
except ImportError:  # namespace-package layout
    from mistralai import workflows as mistralai_workflows

from src.workflows.wordpress import WordPressRequestWorkflow


async def main() -> None:
    await mistralai_workflows.run_worker([WordPressRequestWorkflow])


if __name__ == "__main__":
    asyncio.run(main())
