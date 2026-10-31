"""Unprivileged bounded extraction only. Native code verifies signing and trust.

Never installs, launches an app, reads a profile or accepts a signing key.
"""
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location('update_verify', Path(__file__).with_name('update_verify.py'))
u = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = u
spec.loader.exec_module(u)

def main():
    if len(sys.argv) != 4:
        raise ValueError('Expected archive, metadata and new staging directory.')
    metadata = u.strict_json(Path(sys.argv[2]).read_bytes())
    u.fields(metadata, ('version','sequence','update_epoch','build','channel','url','sha256','size',
                        'minimum_macos','architecture','changelog','manifest_sha256'))
    release = u.VerifiedRelease(**metadata)
    # This callback authorizes no installation: the result remains untrusted
    # staging until the native helper verifies code, platform and signed bytes.
    app = u.stage_archive(sys.argv[1], release, sys.argv[3], verify_bundle=lambda *_: True)
    print(json.dumps({'staged_app':str(app)}))

if __name__ == '__main__':
    main()
