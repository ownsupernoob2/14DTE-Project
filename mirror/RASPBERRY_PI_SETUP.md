# Raspberry Pi Smart Mirror Setup
Run these commands in order. Copy-paste each block exactly.
Your username appears to be "raspi" and your home is /home/raspi — replace if different.

---

## STEP 1: Update packages and install dependencies

```bash
sudo apt update && sudo apt install git python3-full python3-pip -y
```

---

## STEP 2: Clone the repository

```bash
git clone https://github.com/ownsupernoob2/14DTE-Project.git ~/14DTE-Project
```

---

## STEP 3: Create a Python virtual environment

Modern Raspberry Pi OS requires a venv for pip installs.

```bash
python3 -m venv ~/mirror-venv
```

---

## STEP 4: Install Python packages into the venv

```bash
~/mirror-venv/bin/pip install -r ~/14DTE-Project/mirror/requirements.txt
```

This will take a few minutes. Wait for it to fully finish before moving on.

---

## STEP 5: Make the update script executable

```bash
chmod +x ~/14DTE-Project/mirror/update_mirror.sh
```

---

## STEP 6: Set up auto-update cron job (checks GitHub every 5 minutes)

```bash
crontab -e
```

If it asks which editor, press 1 for nano.
Scroll to the very bottom and add this line:

    */5 * * * * /home/raspi/14DTE-Project/mirror/update_mirror.sh >> /home/raspi/mirror_update.log 2>&1

NOTE: If your username is NOT "raspi", replace /home/raspi with your actual home directory.
      You can check what it is by running: echo $HOME

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 7: Set up the mirror to auto-start on boot

```bash
sudo nano /etc/systemd/system/smartmirror.service
```

Paste this entire block into the file (replace "raspi" with your username if different):

    [Unit]
    Description=Smart Mirror
    After=network.target

    [Service]
    User=raspi
    WorkingDirectory=/home/raspi/14DTE-Project/mirror
    ExecStart=/home/raspi/mirror-venv/bin/python /home/raspi/14DTE-Project/mirror/smart_mirror_pro.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 8: Enable and start the mirror service

```bash
sudo systemctl daemon-reload
sudo systemctl enable smartmirror.service
sudo systemctl start smartmirror.service
```

---

## STEP 9: Verify everything is working

Check the mirror service is running:
```bash
sudo systemctl status smartmirror.service
```
You should see "active (running)" in green.

If it shows an error, view the full logs:
```bash
sudo journalctl -u smartmirror.service -n 50
```

Check the auto-update log (wait 5+ minutes first):
```bash
tail -f ~/mirror_update.log
```
Press CTRL+C to stop watching.

---

## Done! Your workflow from now on:

1. Edit code on your Windows PC
2. git push to the main branch on GitHub
3. Within 5 minutes, the Pi automatically pulls the new code and restarts the mirror

---

## Useful Commands (for future reference)

| Command | What it does |
|---|---|
| `sudo systemctl status smartmirror.service` | Check if mirror is running |
| `sudo systemctl restart smartmirror.service` | Manually restart the mirror |
| `sudo systemctl stop smartmirror.service` | Stop the mirror |
| `sudo journalctl -u smartmirror.service -f` | Watch live mirror logs |
| `tail -f ~/mirror_update.log` | Watch the auto-update log |
| `cd ~/14DTE-Project && git pull` | Manually force a git pull |




raspi@raspi:~/14DTE-Project/mirror $ ~/mirror-venv/bin/pip install -r ~/14DTE-Project/mirror/requirements.txt
Looking in indexes: https://pypi.org/simple, https://www.piwheels.org/simple
Collecting opencv-python==4.8.0.74 (from -r /home/raspi/14DTE-Project/mirror/requirements.txt (line 1))
  Downloading opencv_python-4.8.0.74-cp37-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl.metadata (19 kB)
Collecting opencv-contrib-python==4.8.0.74 (from -r /home/raspi/14DTE-Project/mirror/requirements.txt (line 2))
  Downloading opencv_contrib_python-4.8.0.74-cp37-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl.metadata (19 kB)
Collecting numpy==1.24.3 (from -r /home/raspi/14DTE-Project/mirror/requirements.txt (line 3))
  Downloading numpy-1.24.3.tar.gz (10.9 MB)
     ━━━━━━━━━━━━━━━━ 10.9/10.9 MB 7.0 MB/s eta 0:00:00
  Installing build dependencies ... done
  Getting requirements to build wheel ... done
ERROR: Exception:
Traceback (most recent call last):
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/cli/base_command.py", line 105, in _run_wrapper
    status = _inner_run()
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/cli/base_command.py", line 96, in _inner_run
    return self.run(options, args)
           ~~~~~~~~^^^^^^^^^^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/cli/req_command.py", line 68, in wrapper
    return func(self, options, args)
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/commands/install.py", line 387, in run
    requirement_set = resolver.resolve(
        reqs, check_supported_wheels=not options.target_dir
    )
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/resolver.py", line 96, in resolve
    result = self._result = resolver.resolve(
                            ~~~~~~~~~~~~~~~~^
        collected.requirements, max_rounds=limit_how_complex_resolution_can_be
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/resolvelib/resolvers/resolution.py", line 515, in resolve
    state = resolution.resolve(requirements, max_rounds=max_rounds)
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/resolvelib/resolvers/resolution.py", line 388, in resolve
    self._add_to_criteria(self.state.criteria, r, parent=None)
    ~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/resolvelib/resolvers/resolution.py", line 141, in _add_to_criteria
    if not criterion.candidates:
           ^^^^^^^^^^^^^^^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/resolvelib/structs.py", line 194, in __bool__
    return bool(self._sequence)
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py", line 163, in __bool__
    self._bool = any(self)
                 ~~~^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py", line 147, in <genexpr>
    return (c for c in iterator if id(c) not in self._incompatible_ids)
                       ^^^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py", line 37, in _iter_built
    candidate = func()
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/factory.py", line 187, in _make_candidate_from_link
    base: Optional[BaseCandidate] = self._make_base_candidate_from_link(
                                    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
        link, template, name, version
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/factory.py", line 233, in _make_base_candidate_from_link
    self._link_candidate_cache[link] = LinkCandidate(
                                       ~~~~~~~~~~~~~^
        link,
        ^^^^^
    ...<3 lines>...
        version=version,
        ^^^^^^^^^^^^^^^^
    )
    ^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 306, in __init__
    super().__init__(
    ~~~~~~~~~~~~~~~~^
        link=link,
        ^^^^^^^^^^
    ...<4 lines>...
        version=version,
        ^^^^^^^^^^^^^^^^
    )
    ^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 159, in __init__
    self.dist = self._prepare()
                ~~~~~~~~~~~~~^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 236, in _prepare
    dist = self._prepare_distribution()
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 317, in _prepare_distribution
    return preparer.prepare_linked_requirement(self._ireq, parallel_builds=True)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/operations/prepare.py", line 532, in prepare_linked_requirement
    return self._prepare_linked_requirement(req, parallel_builds)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/operations/prepare.py", line 647, in _prepare_linked_requirement
    dist = _get_prepared_distribution(
        req,
    ...<3 lines>...
        self.check_build_deps,
    )
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/operations/prepare.py", line 71, in _get_prepared_distribution
    abstract_dist.prepare_distribution_metadata(
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
        finder, build_isolation, check_build_deps
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/distributions/sdist.py", line 56, in prepare_distribution_metadata
    self._install_build_reqs(finder)
    ~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/distributions/sdist.py", line 126, in _install_build_reqs
    build_reqs = self._get_build_requires_wheel()
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/distributions/sdist.py", line 103, in _get_build_requires_wheel
    return backend.get_requires_for_build_wheel()
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_internal/utils/misc.py", line 702, in get_requires_for_build_wheel
    return super().get_requires_for_build_wheel(config_settings=cs)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/pyproject_hooks/_impl.py", line 196, in get_requires_for_build_wheel
    return self._call_hook(
           ~~~~~~~~~~~~~~~^
        "get_requires_for_build_wheel", {"config_settings": config_settings}
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/pyproject_hooks/_impl.py", line 402, in _call_hook
    raise BackendUnavailable(
    ...<4 lines>...
    )
pip._vendor.pyproject_hooks._impl.BackendUnavailable: Cannot import 'setuptools.build_meta'
raspi@raspi:~/14DTE-Project/mirror $ 
