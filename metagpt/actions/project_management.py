#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/5/11 19:12
@Author  : alexanderwu
@File    : project_management.py
@Modified By: mashenquan, 2023/11/27.
        1. Divide the context into three components: legacy code, unit test code, and console log.
        2. Move the document storage operations related to WritePRD from the save operation of WriteDesign.
        3. According to the design in Section 2.2.3.5.4 of RFC 135, add incremental iteration functionality.
"""
import json

from metagpt.actions import ActionOutput
from metagpt.actions.action import Action
from metagpt.actions.project_management_an import PM_NODE
from metagpt.config import CONFIG
from metagpt.const import (
    PACKAGE_REQUIREMENTS_FILENAME,
    SYSTEM_DESIGN_FILE_REPO,
    TASK_FILE_REPO,
    TASK_PDF_FILE_REPO,
)
from metagpt.logs import logger
from metagpt.schema import Document, Documents
from metagpt.utils.file_repository import FileRepository

# from typing import List

# from metagpt.utils.get_template import get_template

NEW_REQ_TEMPLATE = """
### Legacy Content
{old_tasks}

### New Requirements
{context}
"""


class WriteTasks(Action):
    def __init__(self, name="CreateTasks", context=None, llm=None):
        super().__init__(name, context, llm)

    async def run(self, with_messages, schema=CONFIG.prompt_schema):
        system_design_file_repo = CONFIG.git_repo.new_file_repository(SYSTEM_DESIGN_FILE_REPO)
        changed_system_designs = system_design_file_repo.changed_files

        tasks_file_repo = CONFIG.git_repo.new_file_repository(TASK_FILE_REPO)
        changed_tasks = tasks_file_repo.changed_files
        change_files = Documents()
        # Rewrite the system designs that have undergone changes based on the git head diff under
        # `docs/system_designs/`.
        for filename in changed_system_designs:
            task_doc = await self._update_tasks(
                filename=filename, system_design_file_repo=system_design_file_repo, tasks_file_repo=tasks_file_repo
            )
            change_files.docs[filename] = task_doc

        # Rewrite the task files that have undergone changes based on the git head diff under `docs/tasks/`.
        for filename in changed_tasks:
            if filename in change_files.docs:
                continue
            task_doc = await self._update_tasks(
                filename=filename, system_design_file_repo=system_design_file_repo, tasks_file_repo=tasks_file_repo
            )
            change_files.docs[filename] = task_doc

        if not change_files.docs:
            logger.info("Nothing has changed.")
        # Wait until all files under `docs/tasks/` are processed before sending the publish_message, leaving room for
        # global optimization in subsequent steps.
        return ActionOutput(content=change_files.json(), instruct_content=change_files)

    async def _update_tasks(self, filename, system_design_file_repo, tasks_file_repo):
        system_design_doc = await system_design_file_repo.get(filename)
        task_doc = await tasks_file_repo.get(filename)
        if task_doc:
            task_doc = await self._merge(system_design_doc=system_design_doc, task_doc=task_doc)
        else:
            rsp = await self._run_new_tasks(context=system_design_doc.content)
            task_doc = Document(
                root_path=TASK_FILE_REPO, filename=filename, content=rsp.instruct_content.json(ensure_ascii=False)
            )
        await tasks_file_repo.save(
            filename=filename, content=task_doc.content, dependencies={system_design_doc.root_relative_path}
        )
        await self._update_requirements(task_doc)
        await self._save_pdf(task_doc=task_doc)
        return task_doc

    async def _run_new_tasks(self, context, schema=CONFIG.prompt_schema):
        node = await PM_NODE.fill(context, self.llm, schema)
        # prompt_template, format_example = get_template(templates, format)
        # prompt = prompt_template.format(context=context, format_example=format_example)
        # rsp = await self._aask_v1(prompt, "task", OUTPUT_MAPPING, format=format)
        return node

    async def _merge(self, system_design_doc, task_doc, schema=CONFIG.prompt_schema) -> Document:
        context = NEW_REQ_TEMPLATE.format(context=system_design_doc.content, old_tasks=task_doc.content)
        node = await PM_NODE.fill(context, self.llm, schema)
        task_doc.content = node.instruct_content.json(ensure_ascii=False)
        return task_doc

    @staticmethod
    async def _update_requirements(doc):
        m = json.loads(doc.content)
        packages = set(m.get("Required Python third-party packages", set()))
        file_repo = CONFIG.git_repo.new_file_repository()
        requirement_doc = await file_repo.get(filename=PACKAGE_REQUIREMENTS_FILENAME)
        if not requirement_doc:
            requirement_doc = Document(filename=PACKAGE_REQUIREMENTS_FILENAME, root_path=".", content="")
        lines = requirement_doc.content.splitlines()
        for pkg in lines:
            if pkg == "":
                continue
            packages.add(pkg)
        await file_repo.save(PACKAGE_REQUIREMENTS_FILENAME, content="\n".join(packages))

    @staticmethod
    async def _save_pdf(task_doc):
        await FileRepository.save_as(doc=task_doc, with_suffix=".md", relative_path=TASK_PDF_FILE_REPO)


class AssignTasks(Action):
    async def run(self, *args, **kwargs):
        # Here you should implement the actual action
        pass
