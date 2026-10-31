"""Extract exact bundled license files from verified Windows Python artifacts.

This is a partial inventory. Additional Python native dependencies, Pillow
native libraries, .NET runtime packs and NuGet assets need independent review.
"""
import argparse
import hashlib
from pathlib import Path
from zipfile import ZipFile

ARTIFACTS = {
    'python-3.13.17-embed-amd64.zip': ('9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38', 'LICENSE.txt'),
    'mss-9.0.2-py3-none-any.whl': ('685fa442cc96d8d88b4eb7aadbcccca7b858e789c9259b603e1ef0e435b60425', 'mss-9.0.2.dist-info/licenses/LICENSE.txt'),
    'pillow-13.0.0-cp313-cp313-win_amd64.whl': ('9dda0788a9932776a75d8bcc020076edc308ce2508b51f6739a45e3158b3fc42', 'pillow-13.0.0.dist-info/licenses/LICENSE'),
    'psutil-6.1.0-cp37-abi3-win_amd64.whl': ('a8fb3752b491d246034fa4d279ff076501588ce8cbcdbb62c32fd7a377d996be', 'psutil-6.1.0.dist-info/LICENSE'),
    'uiautomation-2.0.29-py3-none-any.whl': ('5dd51c9e77e70470142a13d903be67f256c445e7cf20b47ada0ece2bdaff9f32', 'uiautomation-2.0.29.dist-info/LICENSE'),
    'comtypes-1.4.17-py3-none-any.whl': ('4e0a221dde2c589b82977bed802efd71cd5eb67a380347b732e02735e597f586', 'comtypes-1.4.17.dist-info/licenses/LICENSE.txt'),
}


def collect(archive, wheelhouse, output):
    sources = [Path(archive)] + [Path(wheelhouse) / name for name in ARTIFACTS if name.endswith('.whl')]
    if len({p.name for p in sources}) != len(ARTIFACTS): raise ValueError('Duplicate or missing artifact names')
    notices = []
    for path in sources:
        expected = ARTIFACTS.get(path.name)
        if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected[0]:
            raise ValueError('Artifact name or SHA-256 mismatch: ' + path.name)
        with ZipFile(path) as archive_file:
            license_text = archive_file.read(expected[1]).decode('utf-8')
        notices.append((path.name, license_text))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'PYTHON.txt').write_bytes(notices[0][1].encode('utf-8'))
    body = '\n\n'.join('==== ' + name + ' ====\n\n' + license_text for name, license_text in notices[1:])
    (output / 'PYTHON-PACKAGES.txt').write_bytes((body + '\n').encode('utf-8'))
    return [name for name, _ in notices]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', required=True)
    parser.add_argument('--wheelhouse', required=True)
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    print('Extracted source notices:', ', '.join(collect(options.archive, options.wheelhouse, options.output)))
    print('Partial inventory: do not treat as legal clearance.')
