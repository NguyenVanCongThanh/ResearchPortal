"""Offline generator bridge, using only source exported by builder.py."""
import ast
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def transform(notebook, options, revision):
    clones = tracking = training = 0
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        text = "".join(cell["source"])
        if "REPO_NAME =" in text and "GITHUB_REPO_URL" in text:
            clones += 1
            # Replace the mutable-branch clone cell with revision-pinned, public clone.
            cell["source"] = [
                "import os, sys, subprocess\n",
                "WORK_DIR = '/kaggle/working/BHSD_SSL'\n",
                "env = os.environ.copy()\nenv['GIT_TERMINAL_PROMPT'] = '0'\n",
                "if not os.path.exists(WORK_DIR):\n    subprocess.run(['git', 'clone', 'https://github.com/NguyenVanCongThanh/BHSD_SSL.git', WORK_DIR], env=env, check=True, timeout=120)\n",
                f"subprocess.run(['git', '-C', WORK_DIR, 'checkout', '--detach', {revision!r}], env=env, check=True, timeout=60)\n",
                f"assert subprocess.check_output(['git', '-C', WORK_DIR, 'rev-parse', 'HEAD'], text=True).strip() == {revision!r}\n",
                "os.chdir(WORK_DIR)\nsys.path.insert(0, WORK_DIR)\n"]
        elif "WANDB_API_KEY =" in text and "wandb.login" in text:
            tracking += 1
            code = "import os, wandb\nWANDB_PROJECT = 'BHSD_MeanTeacher'\nos.environ['WANDB_PROJECT'] = WANDB_PROJECT\n"
            if options["tracking"] == "kaggle_secrets":
                code += ("from kaggle_secrets import UserSecretsClient\n"
                         "key = UserSecretsClient().get_secret('WANDB_API_KEY')\n"
                         "if not key: raise RuntimeError('WANDB_API_KEY Kaggle Secret is required')\n"
                         "os.environ['WANDB_API_KEY'] = key\nos.environ['WANDB_MODE'] = 'online'\n"
                         "wandb.login(key=key, relogin=True)\n")
            else:
                code += "os.environ.pop('WANDB_API_KEY', None)\nos.environ['WANDB_MODE'] = 'offline'\n"
            cell["source"] = code.splitlines(True)
        elif "base_args = [" in text and "# Cấu hình Anti-Deadlock" in text:
            training += 1
            extra = f'    "--experiment.num_classes", "{2 if options["task"] == "binary" else 6}",\n'
            extra += f'    "--logging.wandb_mode", "{"offline" if options["tracking"] == "offline" else "online"}",\n'
            text = text.replace('base_args = [\n', 'base_args = [\n' + extra, 1)
            if options["tracking"] == "offline":
                text = text.replace('    "--wandb_required",\n', '')
            cell["source"] = text.splitlines(True)
    if (clones, tracking, training) != (1, 1, 1):
        raise ValueError("Unexpected Mean Teacher template structure")
    return notebook


def resolved_config(root, notebook, options):
    # Read only literal generator constants, never execute notebook/GPU code.
    training = next("".join(c["source"]) for c in notebook["cells"] if "base_args = [" in "".join(c.get("source", [])))
    tree = ast.parse(training)
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    if constants.get("TASK") != options["task"]:
        raise ValueError("Task mapping changed")
    flags = [("FOLD_ID", "--fold"), ("TASK", "--task"), ("MODEL_NAME", "--model"),
             ("MAX_ITER", "--max_iteration"), ("VAL_INTERVAL", "--val_interval"),
             ("SAVE_INTERVAL", "--save_interval"), ("BATCH_SIZE", "--batch_size"),
             ("LABELED_BS", "--labeled_bs"), ("LABELNUM", "--labelnum")]
    args = [part for key, flag in flags for part in (flag, str(constants[key]))] + ["--amp", "--use_wandb", "--save_wandb_model"]
    args += ["--experiment.num_classes", "2" if options["task"] == "binary" else "6",
             "--logging.wandb_mode", "offline" if options["tracking"] == "offline" else "online"]
    if options["tracking"] == "kaggle_secrets":
        args.append("--wandb_required")
    parser = module(root / "core/config_parser.py", "portal_bhsd_parser")
    config = parser.load_config(config_path=str(root / constants["CONFIG_FILE"]), cli_args=args)
    return {"base_config": dict(config), "runtime_overrides": ["data root", "experiment timestamp/name", "GPU world size"],
            "resume": {"source_run": options["resume_run"], "resolved_on_kaggle": bool(options["resume_run"])} }


def main():
    request = json.load(sys.stdin)
    root, options = Path(request["workspace"]), request["options"]
    with redirect_stdout(io.StringIO()):
        generator = module(root / "tools/generate_mean_teacher_notebook.py", "portal_bhsd_generator")
        notebook = generator.build_mean_teacher_notebook(task=options["task"])
        notebook = transform(notebook, options, request["revision"])
        config = resolved_config(root, notebook, options)
        if options["resume_run"]:
            resume = module(root / "tools/kaggle/resume.py", "portal_bhsd_resume")
            resume.inject_resume(notebook, options["resume_run"], options["checkpoint"] or "latest", options["resume_mode"] or "same-run")
            matches = 0
            for cell in notebook["cells"]:
                text = "".join(cell.get("source", []))
                anchor = "    cfg = copy.deepcopy(dict(run.config))\n"
                if cell.get("cell_type") == "code" and anchor in text:
                    matches += 1
                    guard = (f"    if cfg.get('experiment', {{}}).get('task') != {options['task']!r}:\n"
                             "        raise ValueError('Resume source task differs from reviewed preview')\n")
                    cell["source"] = text.replace(anchor, anchor + guard, 1).splitlines(True)
            if matches != 1:
                raise ValueError("Resume template validation anchor changed")
    print(json.dumps({"notebook": notebook, "resolved_config": config}, default=str))


if __name__ == "__main__":
    main()
