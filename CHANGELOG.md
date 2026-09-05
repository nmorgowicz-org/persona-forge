# Changelog

## [1.4.9](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.8...persona-forge-v1.4.9) (2026-09-05)


### Documentation

* **native:** add root README launcher quick start ([b6be7e4](https://github.com/nmorgowicz-org/persona-forge/commit/b6be7e419211dcaff622c8780c944b9fed417661))

## [1.4.8](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.7...persona-forge-v1.4.8) (2026-09-05)


### Documentation

* **native:** clarify release launcher installation ([cfd93ab](https://github.com/nmorgowicz-org/persona-forge/commit/cfd93abe9d3e3bede5c605481e07453bee95f8d7))

## [1.4.7](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.6...persona-forge-v1.4.7) (2026-09-05)


### Bug Fixes

* **ci:** grant release job contents write permission ([8affc67](https://github.com/nmorgowicz-org/persona-forge/commit/8affc67226211745580e518791ba89d8d790d328))

## [1.4.6](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.5...persona-forge-v1.4.6) (2026-09-05)


### Bug Fixes

* **ci:** use Windows PowerShell for launcher smoke ([c11a527](https://github.com/nmorgowicz-org/persona-forge/commit/c11a527bb3fe5b2a0556f7232165048eb17231b8))

## [1.4.5](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.4...persona-forge-v1.4.5) (2026-09-05)


### Bug Fixes

* **ci:** run Windows launcher smoke test natively ([2eaa960](https://github.com/nmorgowicz-org/persona-forge/commit/2eaa960f24cd5f4a5197bb1f866daf004eac55a5))
* **launcher:** invoke Python after venv promotion ([2eaa960](https://github.com/nmorgowicz-org/persona-forge/commit/2eaa960f24cd5f4a5197bb1f866daf004eac55a5))

## [1.4.4](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.3...persona-forge-v1.4.4) (2026-09-05)


### Bug Fixes

* **ci:** use Rust 1.98 for launcher release builds ([3c5631d](https://github.com/nmorgowicz-org/persona-forge/commit/3c5631d765eacfebb3e06711545fe0631096908c))


### Miscellaneous Chores

* **deps:** track launcher Rust toolchain in Renovate ([3c5631d](https://github.com/nmorgowicz-org/persona-forge/commit/3c5631d765eacfebb3e06711545fe0631096908c))

## [1.4.3](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.2...persona-forge-v1.4.3) (2026-09-05)


### Bug Fixes

* **ci:** run UI path filter on ARC ([15e2ca8](https://github.com/nmorgowicz-org/persona-forge/commit/15e2ca8b23ab61293852e5dc989fa050fe87a695))
* **ci:** use GNU Linux target for launcher release builds ([ea53dcc](https://github.com/nmorgowicz-org/persona-forge/commit/ea53dccc3ceff46fbc9ddb408ff0dd9433521e85))
* **deps:** update rust crate sha2 to 0.11 ([#256](https://github.com/nmorgowicz-org/persona-forge/issues/256)) ([c26c0a9](https://github.com/nmorgowicz-org/persona-forge/commit/c26c0a95eb6255352876207f0a927b697d7a8b7b))
* **renovate:** keep accelerator torch pins manual ([2850d87](https://github.com/nmorgowicz-org/persona-forge/commit/2850d875b7fd1706aba0d41b4598aefc90f220bb))


### Miscellaneous Chores

* **deps:** pin rust crate tempfile to =3.27.0 ([#253](https://github.com/nmorgowicz-org/persona-forge/issues/253)) ([2507665](https://github.com/nmorgowicz-org/persona-forge/commit/2507665c808fc1c9d693c3c9cb9021f7f6d7ef18))
* **deps:** update softprops/action-gh-release digest to efb3536 ([#254](https://github.com/nmorgowicz-org/persona-forge/issues/254)) ([b124519](https://github.com/nmorgowicz-org/persona-forge/commit/b124519bb8c5acd176824e8735124b75f6433d68))

## [1.4.2](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.1...persona-forge-v1.4.2) (2026-09-05)


### Bug Fixes

* **ci:** use arc-llama-monitor for launcher release cross-builds ([44c7e3b](https://github.com/nmorgowicz-org/persona-forge/commit/44c7e3bfbc33ce019ba117d9bdfdd5d64301f30e))
* **ci:** validate launcher preflight for matrix target and Rust toolchain ([44c7e3b](https://github.com/nmorgowicz-org/persona-forge/commit/44c7e3bfbc33ce019ba117d9bdfdd5d64301f30e))

## [1.4.1](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.4.0...persona-forge-v1.4.1) (2026-09-05)


### Bug Fixes

* **release:** install Node before building launcher artifacts ([15b5fea](https://github.com/nmorgowicz-org/persona-forge/commit/15b5fea1c90fff85c426be9936e49b3cc6eb0933))

## [1.4.0](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.3.0...persona-forge-v1.4.0) (2026-09-04)


### Features

* **accelerator:** add native wheel selection without removing container installs ([ba36805](https://github.com/nmorgowicz-org/persona-forge/commit/ba36805fcad71b3832451e67d6fb24f241a4e0c0))
* **cli:** add native setup doctor and serve commands ([ba36805](https://github.com/nmorgowicz-org/persona-forge/commit/ba36805fcad71b3832451e67d6fb24f241a4e0c0))
* **packaging:** distribute the Studio and platform launcher metadata ([ba36805](https://github.com/nmorgowicz-org/persona-forge/commit/ba36805fcad71b3832451e67d6fb24f241a4e0c0))
* **paths:** add native state paths without changing container mounts ([ba36805](https://github.com/nmorgowicz-org/persona-forge/commit/ba36805fcad71b3832451e67d6fb24f241a4e0c0))


### Bug Fixes

* **qwen:** make compatibility patching exhaustive and idempotent ([ba36805](https://github.com/nmorgowicz-org/persona-forge/commit/ba36805fcad71b3832451e67d6fb24f241a4e0c0))
* **release:** keep uv lock synchronized with Release Please ([62f414d](https://github.com/nmorgowicz-org/persona-forge/commit/62f414dddc9090a1c298399e8e5067a02c969b66))


### Documentation

* **setup:** document native container and launcher workflows ([ba36805](https://github.com/nmorgowicz-org/persona-forge/commit/ba36805fcad71b3832451e67d6fb24f241a4e0c0))


### Continuous Integration

* **packaging:** validate native packages and target resolution ([ba36805](https://github.com/nmorgowicz-org/persona-forge/commit/ba36805fcad71b3832451e67d6fb24f241a4e0c0))


### Miscellaneous Chores

* **deps:** update frontend npm dependencies ([#244](https://github.com/nmorgowicz-org/persona-forge/issues/244)) ([7a13c4c](https://github.com/nmorgowicz-org/persona-forge/commit/7a13c4c8eb9af2d33c62e5ccb0f58e09af2a73db))

## [1.3.0](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.2.2...persona-forge-v1.3.0) (2026-09-03)


### Features

* **runtime:** validate native Persona Forge with Torch 2.14 ([9de620c](https://github.com/nmorgowicz-org/persona-forge/commit/9de620c064bff2b0cafe69e4f5aecca151a2ad3e))


### Bug Fixes

* **deps:** adopt tested Torch 2.14 CPU stack ([9de620c](https://github.com/nmorgowicz-org/persona-forge/commit/9de620c064bff2b0cafe69e4f5aecca151a2ad3e))
* **deps:** update dependency pocket-tts to v3.1.0 ([#241](https://github.com/nmorgowicz-org/persona-forge/issues/241)) ([fdc5531](https://github.com/nmorgowicz-org/persona-forge/commit/fdc5531385422e13b9cf42797613318490c2d3c5))
* **security:** avoid exposing transcription exceptions ([9de620c](https://github.com/nmorgowicz-org/persona-forge/commit/9de620c064bff2b0cafe69e4f5aecca151a2ad3e))
* **voice-library:** harden reference transcription workflows ([9de620c](https://github.com/nmorgowicz-org/persona-forge/commit/9de620c064bff2b0cafe69e4f5aecca151a2ad3e))
* **voice-library:** preserve and deduplicate Rosie reference ([9de620c](https://github.com/nmorgowicz-org/persona-forge/commit/9de620c064bff2b0cafe69e4f5aecca151a2ad3e))


### Continuous Integration

* **deps:** gate Torch upgrades on complete stack validation ([9de620c](https://github.com/nmorgowicz-org/persona-forge/commit/9de620c064bff2b0cafe69e4f5aecca151a2ad3e))


### Miscellaneous Chores

* **deps:** bump fast-uri from 3.1.5 to 3.1.7 in /frontend ([#237](https://github.com/nmorgowicz-org/persona-forge/issues/237)) ([f17bf50](https://github.com/nmorgowicz-org/persona-forge/commit/f17bf500a227487e4227d87f5af89bf9aa641794))
* **deps:** bump qs from 6.15.3 to 6.16.0 in /frontend ([#239](https://github.com/nmorgowicz-org/persona-forge/issues/239)) ([9615a60](https://github.com/nmorgowicz-org/persona-forge/commit/9615a60f6252687b15b6e6488a5d2309c8d71c2e))
* **deps:** update dependency lucide-react to v1.37.0 ([#234](https://github.com/nmorgowicz-org/persona-forge/issues/234)) ([f4c9860](https://github.com/nmorgowicz-org/persona-forge/commit/f4c9860e63917225ea85bde0b5f61fa2ce10a6b9))
* **deps:** update dependency lucide-react to v1.38.0 ([#238](https://github.com/nmorgowicz-org/persona-forge/issues/238)) ([e3beead](https://github.com/nmorgowicz-org/persona-forge/commit/e3beead390599e03359df036688249ad7ca75394))
* **deps:** update dependency shadcn to v4.19.1 ([#240](https://github.com/nmorgowicz-org/persona-forge/issues/240)) ([577f22e](https://github.com/nmorgowicz-org/persona-forge/commit/577f22e7c098eb54ed1cd82583320a9a89fef651))
* **deps:** update docker base images ([#231](https://github.com/nmorgowicz-org/persona-forge/issues/231)) ([9866677](https://github.com/nmorgowicz-org/persona-forge/commit/986667730d1ef4e79db973b3c40dd6538c58e405))
* **deps:** update frontend npm dependencies ([#229](https://github.com/nmorgowicz-org/persona-forge/issues/229)) ([bcb777b](https://github.com/nmorgowicz-org/persona-forge/commit/bcb777b5a29203ca8387d5f2cde04da95c228a01))
* **deps:** update frontend npm dependencies ([#232](https://github.com/nmorgowicz-org/persona-forge/issues/232)) ([0ad3135](https://github.com/nmorgowicz-org/persona-forge/commit/0ad31355c85768c142bad0a4961528bda1d41be8))
* **deps:** update github/codeql-action digest to cdf488f ([#228](https://github.com/nmorgowicz-org/persona-forge/issues/228)) ([8945a79](https://github.com/nmorgowicz-org/persona-forge/commit/8945a79780b75e555c2f88aa0d25875d22ba7653))
* **deps:** update python:3.13-slim docker digest to 881d807 ([#233](https://github.com/nmorgowicz-org/persona-forge/issues/233)) ([4321ca3](https://github.com/nmorgowicz-org/persona-forge/commit/4321ca37dfff1e0a515446e45daa33d3e8e5fda5))
* **deps:** update python:3.13-slim docker digest to 9d2e555 ([#235](https://github.com/nmorgowicz-org/persona-forge/issues/235)) ([3acadb2](https://github.com/nmorgowicz-org/persona-forge/commit/3acadb2cd0c23ce2013db3c3c39998c79d13a227))

## [1.2.2](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.2.1...persona-forge-v1.2.2) (2026-08-27)


### Bug Fixes

* **renovate:** correct python-version datasource and group openvino across managers ([#227](https://github.com/nmorgowicz-org/persona-forge/issues/227)) ([1ae0b2d](https://github.com/nmorgowicz-org/persona-forge/commit/1ae0b2d9ed720f141287ca4e46da502a55617f8d))


### Miscellaneous Chores

* **deps:** update dependency @types/react-dom to v19.2.5 ([#225](https://github.com/nmorgowicz-org/persona-forge/issues/225)) ([85e1059](https://github.com/nmorgowicz-org/persona-forge/commit/85e1059fcf827f984300f355120a9e6938f80775))

## [1.2.1](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.2.0...persona-forge-v1.2.1) (2026-08-26)


### Bug Fixes

* **ci:** correct release-please README version-sync output name ([#220](https://github.com/nmorgowicz-org/persona-forge/issues/220)) ([18dd6cf](https://github.com/nmorgowicz-org/persona-forge/commit/18dd6cff274929beb66858c8f3a5d7fd1734590a))
* **deps:** update dependency pocket-tts to v3 ([#218](https://github.com/nmorgowicz-org/persona-forge/issues/218)) ([f7366fc](https://github.com/nmorgowicz-org/persona-forge/commit/f7366fc137411ffbbc5cc96cea5514fd26fde5a8))


### Code Refactoring

* rename lsd_decode_steps to sampler_decode_steps ([#219](https://github.com/nmorgowicz-org/persona-forge/issues/219)) ([06d7982](https://github.com/nmorgowicz-org/persona-forge/commit/06d7982799058604a2ac6d20775298ab73e93ccf))


### Continuous Integration

* bump README image tag via release-please extra-files ([#221](https://github.com/nmorgowicz-org/persona-forge/issues/221)) ([b83caee](https://github.com/nmorgowicz-org/persona-forge/commit/b83caeed87667119ed18ef96b8ecf03c171bb68a))
* bump README image tag via release-please extra-files, not a custom step ([b83caee](https://github.com/nmorgowicz-org/persona-forge/commit/b83caeed87667119ed18ef96b8ecf03c171bb68a))


### Miscellaneous Chores

* **deps:** update dependency shadcn to v4.19.0 ([#215](https://github.com/nmorgowicz-org/persona-forge/issues/215)) ([8f99cd0](https://github.com/nmorgowicz-org/persona-forge/commit/8f99cd0651d7e52709441e015960e58a0ed73030))
* **deps:** update docker base images ([#216](https://github.com/nmorgowicz-org/persona-forge/issues/216)) ([27ca79f](https://github.com/nmorgowicz-org/persona-forge/commit/27ca79fd335737ddc499898e9533cf1c10a32cdf))

## [1.2.0](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.1.4...persona-forge-v1.2.0) (2026-08-24)


### Features

* **runtime:** zero-token Pocket-TTS artifact sourcing with verified provenance ([cb135cb](https://github.com/nmorgowicz-org/persona-forge/commit/cb135cb077187bd031b4f337df853187fb68bff3))


### Bug Fixes

* **deps:** update dependency gunicorn to v26.2.0 ([#214](https://github.com/nmorgowicz-org/persona-forge/issues/214)) ([7bd07ef](https://github.com/nmorgowicz-org/persona-forge/commit/7bd07ef3f903f79589e1f23f8b303ab06270fdcc))


### Miscellaneous Chores

* **ci:** skip Greptile review on Renovate PRs ([cb135cb](https://github.com/nmorgowicz-org/persona-forge/commit/cb135cb077187bd031b4f337df853187fb68bff3))
* **deps:** update frontend npm dependencies ([#210](https://github.com/nmorgowicz-org/persona-forge/issues/210)) ([091d45f](https://github.com/nmorgowicz-org/persona-forge/commit/091d45fda941d7f5f69b7c065ac319d84ebac679))
* **deps:** update omnivoice digest to 08be0b4 ([#212](https://github.com/nmorgowicz-org/persona-forge/issues/212)) ([083c0d7](https://github.com/nmorgowicz-org/persona-forge/commit/083c0d75ff0c43ceae29f84205956308f2bee601))

## [1.1.4](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.1.3...persona-forge-v1.1.4) (2026-08-22)


### Bug Fixes

* **docs:** showcase prosody adjustment feature with hero screenshot ([2b04776](https://github.com/nmorgowicz-org/persona-forge/commit/2b04776c1e084082c6eee6af99ab093b35067efe))

## [1.1.3](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.1.2...persona-forge-v1.1.3) (2026-08-22)


### Bug Fixes

* **docs:** fix broken screenshot refs to actual committed filenames ([6a8903a](https://github.com/nmorgowicz-org/persona-forge/commit/6a8903a0537b5df1de99d67e49c74ce98d2f7b1e))
* **renovate:** close manager-scope gaps letting locked numpy/python upgrades through ([#205](https://github.com/nmorgowicz-org/persona-forge/issues/205)) ([c982025](https://github.com/nmorgowicz-org/persona-forge/commit/c982025e109756562ba09daee9970816d08e97f9))
* **tests:** reset swap/reconfig flags between tier2_backend tests ([6a8903a](https://github.com/nmorgowicz-org/persona-forge/commit/6a8903a0537b5df1de99d67e49c74ce98d2f7b1e))


### Documentation

* add containerization rationale to README, Dockerfile, compose.yml ([6a8903a](https://github.com/nmorgowicz-org/persona-forge/commit/6a8903a0537b5df1de99d67e49c74ce98d2f7b1e))

## [1.1.2](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.1.1...persona-forge-v1.1.2) (2026-08-22)


### Miscellaneous Chores

* **ci:** group Renovate PRs by ecosystem, skip Greptile on release-please ([#201](https://github.com/nmorgowicz-org/persona-forge/issues/201)) ([762aaa3](https://github.com/nmorgowicz-org/persona-forge/commit/762aaa3bc571e7fac4704fa0beadfe2afaf8dd14))
* **deps:** combined dependency updates (gunicorn, oxlint, lucide-react, setup-buildx) ([#202](https://github.com/nmorgowicz-org/persona-forge/issues/202)) ([b1a955b](https://github.com/nmorgowicz-org/persona-forge/commit/b1a955bd0a19f7038ef138254f6781d2f8fb39bf))
* **deps:** update actions/upload-artifact action to v7 ([#194](https://github.com/nmorgowicz-org/persona-forge/issues/194)) ([5581148](https://github.com/nmorgowicz-org/persona-forge/commit/55811487c543bda88df3b3b0855b17d949712133))
* **deps:** update github/codeql-action digest to db488dd ([#197](https://github.com/nmorgowicz-org/persona-forge/issues/197)) ([2d00975](https://github.com/nmorgowicz-org/persona-forge/commit/2d009750acb393feac74feaf3580f19ff73c4f7a))

## [1.1.1](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.1.0...persona-forge-v1.1.1) (2026-08-17)


### Bug Fixes

* **deps:** resolve Renovate allowedVersions error for python pin ([#191](https://github.com/nmorgowicz-org/persona-forge/issues/191)) ([8d200f4](https://github.com/nmorgowicz-org/persona-forge/commit/8d200f4b27f8a597e444be6743ff670b20e98dc9))

## [1.1.0](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.11...persona-forge-v1.1.0) (2026-08-17)


### Features

* **frontend:** list OmniVoice first and default the design engine on pocket_tts ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* **test:** port UI capture harness to split harness/scenarios architecture with contract tests ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))


### Bug Fixes

* **ci:** suppress py/stack-trace-exposure in codeql config for Flask production mode ([bb5e36c](https://github.com/nmorgowicz-org/persona-forge/commit/bb5e36c6d7fe34b7aabfa740b4b9803a9e1a4dde))
* **frontend:** keep /health poller alive and show loading bar on any page ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* **frontend:** self-host Geist Mono and pin rem baseline for cross-platform screenshot determinism ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* **frontend:** show model startup failure in the top status bar ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* **frontend:** suppress js/clear-text-storage for non-sensitive UI breadcrumb ([bb5e36c](https://github.com/nmorgowicz-org/persona-forge/commit/bb5e36c6d7fe34b7aabfa740b4b9803a9e1a4dde))
* **model:** resolve py/path-injection, py/polynomial-redos, py/stack-trace-exposure CodeQL alerts ([bb5e36c](https://github.com/nmorgowicz-org/persona-forge/commit/bb5e36c6d7fe34b7aabfa740b4b9803a9e1a4dde))
* **runtime:** reject Qwen VoiceDesign under pocket_tts before the model swap ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* **runtime:** report startup failure in /health loading_message ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* **runtime:** surface in-flight model loads in /health loading_message ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* **test:** add waveform-readiness waits, stale-receipt guard, and VoiceDesign checkpoint check to capture harness ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))


### Code Refactoring

* **frontend:** remove dead OmniVoice progress polling code ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))


### Tests

* align voice-design-generate capture scenario to neutral runtime ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* assert the saved voice card rather than an absolute count in the Qwen e2e spec ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* find a free capture server port, drop the unimplemented auto source, and remove dead harness code ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* **ui:** assert status bar for base load and startup failure ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))


### Documentation

* document Qwen VoiceDesign unavailability under pocket_tts ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* fix stale product names, dead branch references, and replace banned REF_TEXT example phrases ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* promote curated screenshots into docs/screenshots and rewrite README as a showcase with docs index ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))
* rename dockermisc1 host references to docker-agent ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))


### Miscellaneous Chores

* ignore .serena agent tooling dir ([9d92172](https://github.com/nmorgowicz-org/persona-forge/commit/9d921729bec2f2016352e5641271c8ca86ce923d))

## [1.0.11](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.10...persona-forge-v1.0.11) (2026-08-15)


### Miscellaneous Chores

* **deps:** update actions/cache action to v6 ([#181](https://github.com/nmorgowicz-org/persona-forge/issues/181)) ([8ebad34](https://github.com/nmorgowicz-org/persona-forge/commit/8ebad3432abe5b91a5c1340e354dd7a393bd6caa))
* **deps:** update actions/labeler action to v7 ([#182](https://github.com/nmorgowicz-org/persona-forge/issues/182)) ([f3f8305](https://github.com/nmorgowicz-org/persona-forge/commit/f3f83050446c85d39c73ce30f12e8a3fe3b1f527))
* **deps:** update actions/setup-node action to v6.5.0 ([#178](https://github.com/nmorgowicz-org/persona-forge/issues/178)) ([eb09795](https://github.com/nmorgowicz-org/persona-forge/commit/eb09795e4f3e272038268e4952b8770228b5ecd6))
* **deps:** update actions/setup-node action to v7 ([#183](https://github.com/nmorgowicz-org/persona-forge/issues/183)) ([49ae694](https://github.com/nmorgowicz-org/persona-forge/commit/49ae694e3b0c837ad38a814cbff0036f4bb71e8c))
* **deps:** update actions/setup-python action to v7 ([#184](https://github.com/nmorgowicz-org/persona-forge/issues/184)) ([f8331d9](https://github.com/nmorgowicz-org/persona-forge/commit/f8331d98efd300b841854c1e163ebd129282b463))
* **deps:** update docker/setup-buildx-action digest to bb05f3f ([#175](https://github.com/nmorgowicz-org/persona-forge/issues/175)) ([bdf7af7](https://github.com/nmorgowicz-org/persona-forge/commit/bdf7af790b3860f9de840232e7495ed6fa3ccec0))
* **deps:** update dorny/paths-filter digest to ceb8a2b ([#176](https://github.com/nmorgowicz-org/persona-forge/issues/176)) ([fe36dc3](https://github.com/nmorgowicz-org/persona-forge/commit/fe36dc39afd502ee4064301beb8a510d568715df))
* **deps:** update github/codeql-action digest to ff2f1c6 ([#177](https://github.com/nmorgowicz-org/persona-forge/issues/177)) ([1b7610c](https://github.com/nmorgowicz-org/persona-forge/commit/1b7610c7106aee25cd5253bd269714816a879c00))
* pin Python to 3.13.x and fix transformers disabled rule scope ([#186](https://github.com/nmorgowicz-org/persona-forge/issues/186)) ([ab4b0c3](https://github.com/nmorgowicz-org/persona-forge/commit/ab4b0c3b259666446fb6f54a663573b1f53a9637))

## [1.0.10](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.9...persona-forge-v1.0.10) (2026-08-14)


### Miscellaneous Chores

* **ci:** use legacy-peer-deps for Renovate npm artifact updates ([c47c835](https://github.com/nmorgowicz-org/persona-forge/commit/c47c83571b0ce59166cb68d7b415b2b0def1a2b5))

## [1.0.9](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.8...persona-forge-v1.0.9) (2026-08-14)


### Miscellaneous Chores

* **docs:** ignore local Claude agent config files ([52f8ddb](https://github.com/nmorgowicz-org/persona-forge/commit/52f8ddb9915a609055b2bc292514093e5eb05b86))

## [1.0.8](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.7...persona-forge-v1.0.8) (2026-08-14)


### Bug Fixes

* **frontend:** unblock Generate buttons after idle-unload reloads the model ([3c70e0c](https://github.com/nmorgowicz-org/persona-forge/commit/3c70e0ce918a86e5f7cfc2c845dd140cf18ebc0b))

## [1.0.7](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.6...persona-forge-v1.0.7) (2026-08-13)


### Documentation

* **plans:** close out and archive hermes TTS + rebrand plans ([#156](https://github.com/nmorgowicz-org/persona-forge/issues/156)) ([de68c7a](https://github.com/nmorgowicz-org/persona-forge/commit/de68c7a40465ba97d165e9b8219a28cfe1f04ab8))

## [1.0.6](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.5...persona-forge-v1.0.6) (2026-08-12)


### Bug Fixes

* **model:** ensure Base model is loaded before streaming Pocket-TTS ([80e6795](https://github.com/nmorgowicz-org/persona-forge/commit/80e67955697b78ecf75eaabc9822f639a40dae3f))


### Documentation

* archive llama.cpp pocket-tts pivot plan Phase 1 write-up ([80e6795](https://github.com/nmorgowicz-org/persona-forge/commit/80e67955697b78ecf75eaabc9822f639a40dae3f))


### Miscellaneous Chores

* **deps:** sync uv.lock self-package version with pyproject.toml ([80e6795](https://github.com/nmorgowicz-org/persona-forge/commit/80e67955697b78ecf75eaabc9822f639a40dae3f))

## [1.0.5](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.4...persona-forge-v1.0.5) (2026-08-12)


### Bug Fixes

* **dev:** rebuild persona-forge:local image in dev-deploy.sh instead of only recreating the container ([659a328](https://github.com/nmorgowicz-org/persona-forge/commit/659a32831ef28cef6948f6655c25e89a021f9c8e))


### Documentation

* archive llama.cpp pocket-tts pivot plan as no-go-for-now ([659a328](https://github.com/nmorgowicz-org/persona-forge/commit/659a32831ef28cef6948f6655c25e89a021f9c8e))

## [1.0.4](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.3...persona-forge-v1.0.4) (2026-08-12)


### Bug Fixes

* restore audioop for pydub, stop version string drift ([#150](https://github.com/nmorgowicz-org/persona-forge/issues/150)) ([deb930d](https://github.com/nmorgowicz-org/persona-forge/commit/deb930d8698d4bbe3b0d96c09507eb15e4eb38a4))

## [1.0.3](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.2...persona-forge-v1.0.3) (2026-08-12)


### Bug Fixes

* restore audioop for pydub, stop version string drift ([#148](https://github.com/nmorgowicz-org/persona-forge/issues/148)) ([d8789e7](https://github.com/nmorgowicz-org/persona-forge/commit/d8789e7863f0b5843407796435fec58f53a44ed5))


### Documentation

* **plans:** add llama.cpp native pocket-tts evaluation and pivot plan ([d8789e7](https://github.com/nmorgowicz-org/persona-forge/commit/d8789e7863f0b5843407796435fec58f53a44ed5))

## [1.0.2](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.1...persona-forge-v1.0.2) (2026-08-12)


### Bug Fixes

* **pocket_tts:** stop trimming real trailing speech on quiet sentence endings ([#145](https://github.com/nmorgowicz-org/persona-forge/issues/145)) ([ba24a7f](https://github.com/nmorgowicz-org/persona-forge/commit/ba24a7f3514c1a9a16dab19c01512a1d40c3d2ab))

## [1.0.1](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v1.0.0...persona-forge-v1.0.1) (2026-08-12)


### Bug Fixes

* **ci:** always trigger e2e workflow so it satisfies required status check ([#142](https://github.com/nmorgowicz-org/persona-forge/issues/142)) ([5edb5e9](https://github.com/nmorgowicz-org/persona-forge/commit/5edb5e9f98ce0cabc9a928cf8bfd84a932eadf71))
* **tests:** correct stale applied_steps assertions in test_run_generate ([ece30c6](https://github.com/nmorgowicz-org/persona-forge/commit/ece30c645684ce8f2ce69856d7267f07b6592800))


### Continuous Integration

* add CodeQL analysis workflow ([#141](https://github.com/nmorgowicz-org/persona-forge/issues/141)) ([19aee43](https://github.com/nmorgowicz-org/persona-forge/commit/19aee43ecc54410080bc6096c7422b9148eb9143))


### Miscellaneous Chores

* **deps:** bump torch from 2.12.1 to 2.13.0 ([#140](https://github.com/nmorgowicz-org/persona-forge/issues/140)) ([5cbbf61](https://github.com/nmorgowicz-org/persona-forge/commit/5cbbf61c8f2a70f5bd3e03a30e0ba5a5779e74fd))
* **scripts:** add verify_dependency_bump.sh for torch/transformers bump verification ([ece30c6](https://github.com/nmorgowicz-org/persona-forge/commit/ece30c645684ce8f2ce69856d7267f07b6592800))

## [1.0.0](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v0.24.0...persona-forge-v1.0.0) (2026-08-12)


### ⚠ BREAKING CHANGES

* guided-experience teaching layer complete, force 1.0.0 ([#139](https://github.com/nmorgowicz-org/persona-forge/issues/139))

### Features

* **frontend:** extend glossary with a deep-linkable troubleshooting KB (Initiative C3) ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))
* **frontend:** guided persona-creation wizard for new-voice onboarding (Initiative C5) ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))
* **frontend:** inline take-diagnosis chips deep-link into the troubleshooting glossary (Initiative C4) ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))
* **frontend:** progressive disclosure (guided/expert) mode for power-user controls (Initiative C2) ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))
* **frontend:** shared metric-tooltip seam wired to glossary (Initiative C1) ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))
* **frontend:** update-available notification banner backed by GitHub Releases ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))
* guided-experience teaching layer complete, force 1.0.0 ([#139](https://github.com/nmorgowicz-org/persona-forge/issues/139)) ([238e569](https://github.com/nmorgowicz-org/persona-forge/commit/238e569bbedf8fa598c941a2620a35f5b195c208))
* **runtime:** wire automated take diagnostics into prosody-preview, generate, and omnivoice audition endpoints (Initiative C4) ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))


### Tests

* add audio_diagnostics unit tests ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))


### Documentation

* archive completed post-merge initiatives plan to docs/dev/resolved ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))
* document Release Please version bump rules and Release-As override ([635666b](https://github.com/nmorgowicz-org/persona-forge/commit/635666bf54f484989333d0b5b7bccee2f9d95169))

## [0.24.0](https://github.com/nmorgowicz-org/persona-forge/compare/persona-forge-v0.23.0...persona-forge-v0.24.0) (2026-08-11)


### Features

* add TTS_MAX_SPEECH_SECONDS for configurable stateful capacity ceiling ([47b2706](https://github.com/nmorgowicz-org/persona-forge/commit/47b2706321d9fff7705b71f361aab90268c03508))
* **api:** add OpenAI-compatible /v1/audio/speech endpoint ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **audio_post:** add numpy-based compressor, loudness normalizer, crossfade concat, and drone-detect heuristic ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **backend:** seeded VoiceDesign, per-voice cloning cache, runtime control panel ([1d56671](https://github.com/nmorgowicz-org/persona-forge/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **bench:** add measured 1.7B speed gate (M1.7B-A), with INT4 reaching 1.35x ([679799d](https://github.com/nmorgowicz-org/persona-forge/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* bootstrap configurable OpenVINO TTS service ([#1](https://github.com/nmorgowicz-org/persona-forge/issues/1)) ([8eaea24](https://github.com/nmorgowicz-org/persona-forge/commit/8eaea2491cc7a339671f020903115068eecdd121))
* **docker:** unified export service with EXPORT_TARGET=both for Base + VoiceDesign; simplified compose.yml and .env.example ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **export:** add INT4 precision-tagged artifact directories and document M7-M9 findings ([679799d](https://github.com/nmorgowicz-org/persona-forge/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **export:** add Milestone 2 transformer core parity gate for main and predictor cores ([fc527f5](https://github.com/nmorgowicz-org/persona-forge/commit/fc527f5263bb553f462755bcab999fbf3300a200))
* **export:** add vocoder decoder export as Milestone 1.5 ([2bff1da](https://github.com/nmorgowicz-org/persona-forge/commit/2bff1da1ed88aeb9543b280714e4a55eeb6298eb))
* **export:** complete Milestone 1.5 vocoder decoder export, parity gate, and benchmark ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** data-aware INT8 calibration (scale_estimation) scaffold ([8739289](https://github.com/nmorgowicz-org/persona-forge/commit/87392896d8db155ea541ad8cc70251926c4e429b))
* **export:** infer stateful IR layout and record artifact provenance ([7a7b091](https://github.com/nmorgowicz-org/persona-forge/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **export:** Milestone 1.5 vocoder decoder export + fix CI exporter smoke test ([#10](https://github.com/nmorgowicz-org/persona-forge/issues/10)) ([d2b9649](https://github.com/nmorgowicz-org/persona-forge/commit/d2b964936264d8c9c2698b20d030257a67abf358))
* **export:** relax provenance fields to best-effort non-blocking defaults ([e9d9943](https://github.com/nmorgowicz-org/persona-forge/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **frontend:** add AccentBank with regional accent examples and guidance ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **frontend:** add Persona Forge OmniVoice panel with accent chips, segment audition, and streaming results ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **frontend:** add Pocket TTS options and tuning controls to RuntimeConfigPage; PocketTTSWarningBanner for cloning unavailability ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **frontend:** add standalone Stitch Studio page and Saved Segments browser to Voice Library ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **frontend:** add VST-style Stitch Timeline editor for per-clip trim/fade/gap controls and drag-and-drop reorder ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **frontend:** complete VoiceDesign web UI ([1d56671](https://github.com/nmorgowicz-org/persona-forge/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **frontend:** implement aligned prosody editing and nudge controls ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **frontend:** implement aligned prosody editing and nudge controls ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **frontend:** implement aligned prosody editing and nudge controls ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **frontend:** implement aligned prosody editing and nudge controls ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **frontend:** implement aligned prosody editing and nudge controls ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **frontend:** implement aligned prosody editing and nudge controls ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **frontend:** implement aligned prosody editing and nudge controls ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **frontend:** implement aligned prosody editing and nudge controls ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **frontend:** implement aligned prosody editing and nudge controls ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **frontend:** implement aligned prosody editing and nudge controls ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **frontend:** implement aligned prosody editing and nudge controls ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **frontend:** implement aligned prosody editing and nudge controls ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **frontend:** implement aligned prosody editing and nudge controls ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **frontend:** implement aligned prosody editing and nudge controls ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **frontend:** implement aligned prosody editing and nudge controls ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **frontend:** implement aligned prosody editing and nudge controls ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **frontend:** implement aligned prosody editing and nudge controls ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **frontend:** implement aligned prosody editing and nudge controls ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **frontend:** implement aligned prosody editing and nudge controls ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **frontend:** implement aligned prosody editing and nudge controls ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **frontend:** implement aligned prosody editing and nudge controls ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **frontend:** implement aligned prosody editing and nudge controls ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **frontend:** implement aligned prosody editing and nudge controls ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **frontend:** implement aligned prosody editing and nudge controls ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **frontend:** implement aligned prosody editing and nudge controls ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **frontend:** implement aligned prosody editing and nudge controls ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **frontend:** implement aligned prosody editing and nudge controls ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **frontend:** implement aligned prosody editing and nudge controls ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **frontend:** implement aligned prosody editing and nudge controls ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **frontend:** implement aligned prosody editing and nudge controls ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **frontend:** implement aligned prosody editing and nudge controls ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **frontend:** implement aligned prosody editing and nudge controls ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **frontend:** implement aligned prosody editing and nudge controls ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **frontend:** implement aligned prosody editing and nudge controls ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **frontend:** implement aligned prosody editing and nudge controls ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **frontend:** implement aligned prosody editing and nudge controls ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **frontend:** implement aligned prosody editing and nudge controls ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **frontend:** implement aligned prosody editing and nudge controls ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **frontend:** implement aligned prosody editing and nudge controls ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **frontend:** implement aligned prosody editing and nudge controls ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **frontend:** implement aligned prosody editing and nudge controls ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **frontend:** implement aligned prosody editing and nudge controls ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **frontend:** implement aligned prosody editing and nudge controls ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **frontend:** implement aligned prosody editing and nudge controls ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **frontend:** implement aligned prosody editing and nudge controls ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **frontend:** implement aligned prosody editing and nudge controls ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **frontend:** implement aligned prosody editing and nudge controls ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **frontend:** implement aligned prosody editing and nudge controls ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **frontend:** implement aligned prosody editing and nudge controls ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **frontend:** implement aligned prosody editing and nudge controls ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **frontend:** implement aligned prosody editing and nudge controls ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **frontend:** implement aligned prosody editing and nudge controls ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **frontend:** implement aligned prosody editing and nudge controls ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **frontend:** implement aligned prosody editing and nudge controls ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **frontend:** implement aligned prosody editing and nudge controls ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **frontend:** implement aligned prosody editing and nudge controls ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **frontend:** implement aligned prosody editing and nudge controls ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **frontend:** implement aligned prosody editing and nudge controls ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **frontend:** implement aligned prosody editing and nudge controls ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **frontend:** implement aligned prosody editing and nudge controls ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **frontend:** implement aligned prosody editing and nudge controls ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **frontend:** implement aligned prosody editing and nudge controls ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **frontend:** implement aligned prosody editing and nudge controls ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **frontend:** implement aligned prosody editing and nudge controls ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **frontend:** implement aligned prosody editing and nudge controls ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **frontend:** implement aligned prosody editing and nudge controls ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **frontend:** implement aligned prosody editing and nudge controls ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **frontend:** implement aligned prosody editing and nudge controls ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **frontend:** implement aligned prosody editing and nudge controls ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **frontend:** implement aligned prosody editing and nudge controls ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **frontend:** implement aligned prosody editing and nudge controls ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **frontend:** implement aligned prosody editing and nudge controls ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **frontend:** implement aligned prosody editing and nudge controls ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **frontend:** implement aligned prosody editing and nudge controls ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **frontend:** implement aligned prosody editing and nudge controls ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **frontend:** implement aligned prosody editing and nudge controls ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **frontend:** implement aligned prosody editing and nudge controls ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **frontend:** implement aligned prosody editing and nudge controls ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **frontend:** implement aligned prosody editing and nudge controls ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **frontend:** implement aligned prosody editing and nudge controls ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **frontend:** implement aligned prosody editing and nudge controls ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **frontend:** implement aligned prosody editing and nudge controls ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **frontend:** implement aligned prosody editing and nudge controls ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **frontend:** implement aligned prosody editing and nudge controls ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **frontend:** implement aligned prosody editing and nudge controls ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **frontend:** implement aligned prosody editing and nudge controls ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **frontend:** implement aligned prosody editing and nudge controls ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **frontend:** implement aligned prosody editing and nudge controls ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **frontend:** implement aligned prosody editing and nudge controls ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **frontend:** implement aligned prosody editing and nudge controls ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **frontend:** implement aligned prosody editing and nudge controls ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **frontend:** implement aligned prosody editing and nudge controls ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **frontend:** implement aligned prosody editing and nudge controls ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **frontend:** implement aligned prosody editing and nudge controls ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **frontend:** implement aligned prosody editing and nudge controls ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **frontend:** implement aligned prosody editing and nudge controls ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **frontend:** implement aligned prosody editing and nudge controls ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **frontend:** implement aligned prosody editing and nudge controls ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **frontend:** implement aligned prosody editing and nudge controls ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **frontend:** implement aligned prosody editing and nudge controls ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **frontend:** implement aligned prosody editing and nudge controls ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **frontend:** implement aligned prosody editing and nudge controls ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **frontend:** implement aligned prosody editing and nudge controls ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **frontend:** implement aligned prosody editing and nudge controls ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **frontend:** implement aligned prosody editing and nudge controls ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **frontend:** implement aligned prosody editing and nudge controls ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **frontend:** implement aligned prosody editing and nudge controls ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **frontend:** implement aligned prosody editing and nudge controls ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **frontend:** implement aligned prosody editing and nudge controls ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **frontend:** implement aligned prosody editing and nudge controls ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **frontend:** implement aligned prosody editing and nudge controls ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **frontend:** implement aligned prosody editing and nudge controls ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **frontend:** implement aligned prosody editing and nudge controls ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **frontend:** implement aligned prosody editing and nudge controls ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **frontend:** implement aligned prosody editing and nudge controls ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **frontend:** implement aligned prosody editing and nudge controls ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **frontend:** implement aligned prosody editing and nudge controls ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **frontend:** implement aligned prosody editing and nudge controls ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **frontend:** implement aligned prosody editing and nudge controls ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **frontend:** implement aligned prosody editing and nudge controls ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **frontend:** implement aligned prosody editing and nudge controls ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **frontend:** implement aligned prosody editing and nudge controls ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **frontend:** implement aligned prosody editing and nudge controls ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **frontend:** implement stacked waveform A/B comparison and inline prosody deltas ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **frontend:** implement voice library UI and reference audio editor ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **frontend:** implement voice library UI and reference audio editor ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **frontend:** implement voice library UI and reference audio editor ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **frontend:** implement voice library UI and reference audio editor ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **frontend:** implement voice library UI and reference audio editor ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **frontend:** implement voice library UI and reference audio editor ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **frontend:** implement voice library UI and reference audio editor ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **frontend:** implement voice library UI and reference audio editor ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **frontend:** implement voice library UI and reference audio editor ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **frontend:** implement voice library UI and reference audio editor ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **frontend:** implement voice library UI and reference audio editor ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **frontend:** implement voice library UI and reference audio editor ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **frontend:** implement voice library UI and reference audio editor ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **frontend:** implement voice library UI and reference audio editor ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **frontend:** implement voice library UI and reference audio editor ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **frontend:** implement voice library UI and reference audio editor ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **frontend:** implement voice library UI and reference audio editor ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **frontend:** implement voice library UI and reference audio editor ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **frontend:** implement voice library UI and reference audio editor ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **frontend:** implement voice library UI and reference audio editor ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **frontend:** implement voice library UI and reference audio editor ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **frontend:** implement voice library UI and reference audio editor ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **frontend:** implement voice library UI and reference audio editor ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **frontend:** implement voice library UI and reference audio editor ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **frontend:** implement voice library UI and reference audio editor ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **frontend:** implement voice library UI and reference audio editor ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **frontend:** implement voice library UI and reference audio editor ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **frontend:** implement voice library UI and reference audio editor ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **frontend:** implement voice library UI and reference audio editor ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **frontend:** implement voice library UI and reference audio editor ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **frontend:** implement voice library UI and reference audio editor ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **frontend:** implement voice library UI and reference audio editor ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **frontend:** implement voice library UI and reference audio editor ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **frontend:** implement voice library UI and reference audio editor ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **frontend:** implement voice library UI and reference audio editor ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **frontend:** implement voice library UI and reference audio editor ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **frontend:** implement voice library UI and reference audio editor ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **frontend:** implement voice library UI and reference audio editor ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **frontend:** implement voice library UI and reference audio editor ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **frontend:** implement voice library UI and reference audio editor ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **frontend:** implement voice library UI and reference audio editor ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **frontend:** implement voice library UI and reference audio editor ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **frontend:** implement voice library UI and reference audio editor ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **frontend:** implement voice library UI and reference audio editor ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **frontend:** implement voice library UI and reference audio editor ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **frontend:** implement voice library UI and reference audio editor ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **frontend:** implement voice library UI and reference audio editor ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **frontend:** implement voice library UI and reference audio editor ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **frontend:** implement voice library UI and reference audio editor ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **frontend:** implement voice library UI and reference audio editor ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **frontend:** implement voice library UI and reference audio editor ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **frontend:** implement voice library UI and reference audio editor ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **frontend:** implement voice library UI and reference audio editor ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **frontend:** implement voice library UI and reference audio editor ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **frontend:** implement voice library UI and reference audio editor ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **frontend:** implement voice library UI and reference audio editor ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **frontend:** implement voice library UI and reference audio editor ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **frontend:** implement voice library UI and reference audio editor ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **frontend:** implement voice library UI and reference audio editor ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **frontend:** implement voice library UI and reference audio editor ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **frontend:** implement voice library UI and reference audio editor ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **frontend:** implement voice library UI and reference audio editor ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **frontend:** implement voice library UI and reference audio editor ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **frontend:** implement voice library UI and reference audio editor ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **frontend:** implement voice library UI and reference audio editor ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **frontend:** implement voice library UI and reference audio editor ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **frontend:** implement voice library UI and reference audio editor ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **frontend:** implement voice library UI and reference audio editor ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **frontend:** implement voice library UI and reference audio editor ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **frontend:** implement voice library UI and reference audio editor ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **frontend:** implement voice library UI and reference audio editor ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **frontend:** implement voice library UI and reference audio editor ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **frontend:** implement voice library UI and reference audio editor ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **frontend:** implement voice library UI and reference audio editor ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **frontend:** implement voice library UI and reference audio editor ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **frontend:** implement voice library UI and reference audio editor ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **frontend:** implement voice library UI and reference audio editor ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **frontend:** implement voice library UI and reference audio editor ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **frontend:** implement voice library UI and reference audio editor ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **frontend:** implement voice library UI and reference audio editor ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **frontend:** implement voice library UI and reference audio editor ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **frontend:** implement voice library UI and reference audio editor ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **frontend:** implement voice library UI and reference audio editor ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **frontend:** implement voice library UI and reference audio editor ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **frontend:** implement voice library UI and reference audio editor ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **frontend:** implement voice library UI and reference audio editor ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **frontend:** implement voice library UI and reference audio editor ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **frontend:** implement voice library UI and reference audio editor ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **frontend:** implement voice library UI and reference audio editor ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **frontend:** implement voice library UI and reference audio editor ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **frontend:** implement voice library UI and reference audio editor ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **frontend:** implement voice library UI and reference audio editor ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **frontend:** implement voice library UI and reference audio editor ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **frontend:** implement voice library UI and reference audio editor ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **frontend:** implement voice library UI and reference audio editor ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **frontend:** implement voice library UI and reference audio editor ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **frontend:** implement voice library UI and reference audio editor ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **frontend:** implement voice library UI and reference audio editor ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **frontend:** implement voice library UI and reference audio editor ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **frontend:** implement voice library UI and reference audio editor ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **frontend:** implement voice library UI and reference audio editor ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **frontend:** implement voice library UI and reference audio editor ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **frontend:** implement voice library UI and reference audio editor ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **frontend:** implement voice library UI and reference audio editor ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **frontend:** implement voice library UI and reference audio editor ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **frontend:** implement voice library UI and reference audio editor ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **frontend:** implement voice library UI and reference audio editor ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **frontend:** implement voice library UI and reference audio editor ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **frontend:** implement voice library UI and reference audio editor ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **frontend:** implement voice library UI and reference audio editor ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **frontend:** implement voice library UI and reference audio editor ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **frontend:** implement voice library UI and reference audio editor ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **frontend:** implement voice library UI and reference audio editor ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **frontend:** implement voice library UI and reference audio editor ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **frontend:** implement voice library UI and reference audio editor ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **frontend:** implement voice library UI and reference audio editor ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **frontend:** implement voice library UI and reference audio editor ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **frontend:** implement voice library UI and reference audio editor ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **frontend:** implement voice library UI and reference audio editor ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **frontend:** implement voice library UI and reference audio editor ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **frontend:** implement voice library UI and reference audio editor ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **frontend:** implement voice library UI and reference audio editor ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **frontend:** implement voice library UI and reference audio editor ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **health:** report active stateful cores and cache capacities ([7a7b091](https://github.com/nmorgowicz-org/persona-forge/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **infra:** LOW_RAM_MODE with jemalloc allocator and entrypoint ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **m4:** buffer-backed K/V cache with OPENVINO_BUFFER_KV guard and bench env helper ([a78be3d](https://github.com/nmorgowicz-org/persona-forge/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **m4:** wire OpenVINO vocoder IR into the runtime with PyTorch fallback ([a78be3d](https://github.com/nmorgowicz-org/persona-forge/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **m9:** add exact ru_maxrss per-phase attribution to find the generation transient$'\n\n'feat(m9): localize lifetime peak to PyTorch model-load transient$'\n\n'feat(m9): bf16 serving load to eliminate the fp32 load-transient boot spike ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** add pytorch-vs-stateful parity mode to test_stateful_main_parity ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** add static stateful main cache spike with parity test ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** FP32-vs-PyTorch parity (0.6B) and per-mode max_abs tolerance ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** reduce 1.7B generation memory with stateful main cache and early PyTorch weight release ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** wire OPENVINO_MAIN_STATEFUL_MODEL and OPENVINO_RELEASE_TORCH in app_worker ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **model:** implement punctuation-aware prosody and reference audio variants ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **model:** implement punctuation-aware prosody and reference audio variants ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **model:** implement punctuation-aware prosody and reference audio variants ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **model:** implement punctuation-aware prosody and reference audio variants ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **model:** implement punctuation-aware prosody and reference audio variants ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **model:** implement punctuation-aware prosody and reference audio variants ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **model:** implement punctuation-aware prosody and reference audio variants ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **model:** implement punctuation-aware prosody and reference audio variants ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **model:** implement punctuation-aware prosody and reference audio variants ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **model:** implement punctuation-aware prosody and reference audio variants ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **model:** implement punctuation-aware prosody and reference audio variants ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **model:** implement punctuation-aware prosody and reference audio variants ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **model:** implement punctuation-aware prosody and reference audio variants ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **model:** implement punctuation-aware prosody and reference audio variants ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **model:** implement punctuation-aware prosody and reference audio variants ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **model:** implement punctuation-aware prosody and reference audio variants ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **model:** implement punctuation-aware prosody and reference audio variants ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **model:** implement punctuation-aware prosody and reference audio variants ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **model:** implement punctuation-aware prosody and reference audio variants ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **model:** implement punctuation-aware prosody and reference audio variants ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **model:** implement punctuation-aware prosody and reference audio variants ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **model:** implement punctuation-aware prosody and reference audio variants ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **model:** implement punctuation-aware prosody and reference audio variants ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **model:** implement punctuation-aware prosody and reference audio variants ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **model:** implement punctuation-aware prosody and reference audio variants ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **model:** implement punctuation-aware prosody and reference audio variants ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **model:** implement punctuation-aware prosody and reference audio variants ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **model:** implement punctuation-aware prosody and reference audio variants ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **model:** implement punctuation-aware prosody and reference audio variants ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **model:** implement punctuation-aware prosody and reference audio variants ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **model:** implement punctuation-aware prosody and reference audio variants ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **model:** implement punctuation-aware prosody and reference audio variants ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **model:** implement punctuation-aware prosody and reference audio variants ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **model:** implement punctuation-aware prosody and reference audio variants ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **model:** implement punctuation-aware prosody and reference audio variants ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **model:** implement punctuation-aware prosody and reference audio variants ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **model:** implement punctuation-aware prosody and reference audio variants ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **model:** implement punctuation-aware prosody and reference audio variants ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **model:** implement punctuation-aware prosody and reference audio variants ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **model:** implement punctuation-aware prosody and reference audio variants ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **model:** implement punctuation-aware prosody and reference audio variants ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **model:** implement punctuation-aware prosody and reference audio variants ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **model:** implement punctuation-aware prosody and reference audio variants ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **model:** implement punctuation-aware prosody and reference audio variants ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **model:** implement punctuation-aware prosody and reference audio variants ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **model:** implement punctuation-aware prosody and reference audio variants ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **model:** implement punctuation-aware prosody and reference audio variants ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **model:** implement punctuation-aware prosody and reference audio variants ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **model:** implement punctuation-aware prosody and reference audio variants ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **model:** implement punctuation-aware prosody and reference audio variants ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **model:** implement punctuation-aware prosody and reference audio variants ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **model:** implement punctuation-aware prosody and reference audio variants ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **model:** implement punctuation-aware prosody and reference audio variants ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **model:** implement punctuation-aware prosody and reference audio variants ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **model:** implement punctuation-aware prosody and reference audio variants ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **model:** implement punctuation-aware prosody and reference audio variants ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **model:** implement punctuation-aware prosody and reference audio variants ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **model:** implement punctuation-aware prosody and reference audio variants ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **model:** implement punctuation-aware prosody and reference audio variants ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **model:** implement punctuation-aware prosody and reference audio variants ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **model:** implement punctuation-aware prosody and reference audio variants ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **model:** implement punctuation-aware prosody and reference audio variants ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **model:** implement punctuation-aware prosody and reference audio variants ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **model:** implement punctuation-aware prosody and reference audio variants ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **model:** implement punctuation-aware prosody and reference audio variants ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **model:** implement punctuation-aware prosody and reference audio variants ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **model:** implement punctuation-aware prosody and reference audio variants ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **model:** implement punctuation-aware prosody and reference audio variants ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **model:** implement punctuation-aware prosody and reference audio variants ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **model:** implement punctuation-aware prosody and reference audio variants ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **model:** implement punctuation-aware prosody and reference audio variants ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **model:** implement punctuation-aware prosody and reference audio variants ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **model:** implement punctuation-aware prosody and reference audio variants ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **model:** implement punctuation-aware prosody and reference audio variants ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **model:** implement punctuation-aware prosody and reference audio variants ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **model:** implement punctuation-aware prosody and reference audio variants ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **model:** implement punctuation-aware prosody and reference audio variants ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **model:** implement punctuation-aware prosody and reference audio variants ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **model:** implement punctuation-aware prosody and reference audio variants ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **model:** implement punctuation-aware prosody and reference audio variants ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **model:** implement punctuation-aware prosody and reference audio variants ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **model:** implement punctuation-aware prosody and reference audio variants ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **model:** implement punctuation-aware prosody and reference audio variants ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **model:** implement punctuation-aware prosody and reference audio variants ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **model:** implement punctuation-aware prosody and reference audio variants ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **model:** implement punctuation-aware prosody and reference audio variants ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **model:** implement punctuation-aware prosody and reference audio variants ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **model:** implement punctuation-aware prosody and reference audio variants ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **model:** implement punctuation-aware prosody and reference audio variants ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **model:** implement punctuation-aware prosody and reference audio variants ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **model:** implement punctuation-aware prosody and reference audio variants ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **model:** implement punctuation-aware prosody and reference audio variants ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **model:** implement punctuation-aware prosody and reference audio variants ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **model:** implement punctuation-aware prosody and reference audio variants ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **model:** implement punctuation-aware prosody and reference audio variants ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **model:** implement punctuation-aware prosody and reference audio variants ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **model:** implement punctuation-aware prosody and reference audio variants ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **model:** implement punctuation-aware prosody and reference audio variants ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **model:** implement punctuation-aware prosody and reference audio variants ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **model:** implement punctuation-aware prosody and reference audio variants ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **model:** implement punctuation-aware prosody and reference audio variants ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **model:** implement punctuation-aware prosody and reference audio variants ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **model:** implement punctuation-aware prosody and reference audio variants ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **model:** implement punctuation-aware prosody and reference audio variants ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **model:** implement punctuation-aware prosody and reference audio variants ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **model:** implement punctuation-aware prosody and reference audio variants ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **model:** implement punctuation-aware prosody and reference audio variants ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **model:** implement punctuation-aware prosody and reference audio variants ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **model:** implement punctuation-aware prosody and reference audio variants ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **model:** implement punctuation-aware prosody and reference audio variants ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **model:** implement punctuation-aware prosody and reference audio variants ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **model:** implement punctuation-aware prosody and reference audio variants ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **model:** implement punctuation-aware prosody and reference audio variants ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **model:** implement punctuation-aware prosody and reference audio variants ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **model:** implement punctuation-aware prosody and reference audio variants ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **model:** implement punctuation-aware prosody and reference audio variants ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **model:** implement punctuation-aware prosody and reference audio variants ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **model:** implement punctuation-aware prosody and reference audio variants ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **model:** implement punctuation-aware prosody and reference audio variants ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **model:** implement punctuation-aware prosody and reference audio variants ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **model:** implement punctuation-aware prosody and reference audio variants ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **model:** implement punctuation-aware prosody and reference audio variants ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **model:** implement punctuation-aware prosody and reference audio variants ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **model:** update model to support voice style parameters ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **model:** update model to support voice style parameters ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **model:** update model to support voice style parameters ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **model:** update model to support voice style parameters ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **model:** update model to support voice style parameters ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **model:** update model to support voice style parameters ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **model:** update model to support voice style parameters ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **model:** update model to support voice style parameters ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **model:** update model to support voice style parameters ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **model:** update model to support voice style parameters ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **model:** update model to support voice style parameters ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **model:** update model to support voice style parameters ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **model:** update model to support voice style parameters ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **model:** update model to support voice style parameters ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **model:** update model to support voice style parameters ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **model:** update model to support voice style parameters ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **model:** update model to support voice style parameters ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **model:** update model to support voice style parameters ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **model:** update model to support voice style parameters ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **model:** update model to support voice style parameters ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **model:** update model to support voice style parameters ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **model:** update model to support voice style parameters ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **model:** update model to support voice style parameters ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **model:** update model to support voice style parameters ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **model:** update model to support voice style parameters ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **model:** update model to support voice style parameters ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **model:** update model to support voice style parameters ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **model:** update model to support voice style parameters ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **model:** update model to support voice style parameters ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **model:** update model to support voice style parameters ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **model:** update model to support voice style parameters ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **model:** update model to support voice style parameters ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **model:** update model to support voice style parameters ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **model:** update model to support voice style parameters ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **model:** update model to support voice style parameters ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **model:** update model to support voice style parameters ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **model:** update model to support voice style parameters ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **model:** update model to support voice style parameters ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **model:** update model to support voice style parameters ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **model:** update model to support voice style parameters ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **model:** update model to support voice style parameters ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **model:** update model to support voice style parameters ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **model:** update model to support voice style parameters ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **model:** update model to support voice style parameters ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **model:** update model to support voice style parameters ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **model:** update model to support voice style parameters ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **model:** update model to support voice style parameters ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **model:** update model to support voice style parameters ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **model:** update model to support voice style parameters ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **model:** update model to support voice style parameters ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **model:** update model to support voice style parameters ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **model:** update model to support voice style parameters ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **model:** update model to support voice style parameters ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **model:** update model to support voice style parameters ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **model:** update model to support voice style parameters ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **model:** update model to support voice style parameters ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **model:** update model to support voice style parameters ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **model:** update model to support voice style parameters ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **model:** update model to support voice style parameters ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **model:** update model to support voice style parameters ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **model:** update model to support voice style parameters ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **model:** update model to support voice style parameters ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **model:** update model to support voice style parameters ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **model:** update model to support voice style parameters ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **model:** update model to support voice style parameters ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **model:** update model to support voice style parameters ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **model:** update model to support voice style parameters ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **model:** update model to support voice style parameters ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **model:** update model to support voice style parameters ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **model:** update model to support voice style parameters ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **model:** update model to support voice style parameters ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **model:** update model to support voice style parameters ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **model:** update model to support voice style parameters ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **model:** update model to support voice style parameters ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **model:** update model to support voice style parameters ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **model:** update model to support voice style parameters ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **model:** update model to support voice style parameters ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **model:** update model to support voice style parameters ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **model:** update model to support voice style parameters ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **model:** update model to support voice style parameters ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **model:** update model to support voice style parameters ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **model:** update model to support voice style parameters ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **model:** update model to support voice style parameters ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **model:** update model to support voice style parameters ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **model:** update model to support voice style parameters ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **model:** update model to support voice style parameters ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **model:** update model to support voice style parameters ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **model:** update model to support voice style parameters ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **model:** update model to support voice style parameters ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **model:** update model to support voice style parameters ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **model:** update model to support voice style parameters ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **model:** update model to support voice style parameters ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **model:** update model to support voice style parameters ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **model:** update model to support voice style parameters ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **model:** update model to support voice style parameters ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **model:** update model to support voice style parameters ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **model:** update model to support voice style parameters ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **model:** update model to support voice style parameters ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **model:** update model to support voice style parameters ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **model:** update model to support voice style parameters ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **model:** update model to support voice style parameters ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **model:** update model to support voice style parameters ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **model:** update model to support voice style parameters ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **model:** update model to support voice style parameters ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **model:** update model to support voice style parameters ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **model:** update model to support voice style parameters ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **model:** update model to support voice style parameters ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **model:** update model to support voice style parameters ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **model:** update model to support voice style parameters ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **model:** update model to support voice style parameters ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **model:** update model to support voice style parameters ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **model:** update model to support voice style parameters ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **model:** update model to support voice style parameters ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **model:** update model to support voice style parameters ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **model:** update model to support voice style parameters ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **model:** update model to support voice style parameters ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **model:** update model to support voice style parameters ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **model:** update model to support voice style parameters ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **model:** update model to support voice style parameters ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **model:** update model to support voice style parameters ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **model:** update model to support voice style parameters ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **model:** update model to support voice style parameters ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **model:** update model to support voice style parameters ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **openvino:** add OmniVoice accent-design engine with multi-candidate audition, segment library, and streaming progress API ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **openvino:** implement voice style foundation and orchestration layer ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **openvino:** implement voice style foundation and orchestration layer ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **openvino:** implement voice style foundation and orchestration layer ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **openvino:** implement voice style foundation and orchestration layer ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **openvino:** implement voice style foundation and orchestration layer ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **openvino:** implement voice style foundation and orchestration layer ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **openvino:** implement voice style foundation and orchestration layer ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **openvino:** implement voice style foundation and orchestration layer ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **openvino:** implement voice style foundation and orchestration layer ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **openvino:** implement voice style foundation and orchestration layer ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **openvino:** implement voice style foundation and orchestration layer ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **openvino:** implement voice style foundation and orchestration layer ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **openvino:** implement voice style foundation and orchestration layer ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **openvino:** implement voice style foundation and orchestration layer ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **openvino:** implement voice style foundation and orchestration layer ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **openvino:** implement voice style foundation and orchestration layer ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **openvino:** implement voice style foundation and orchestration layer ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **openvino:** implement voice style foundation and orchestration layer ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **openvino:** implement voice style foundation and orchestration layer ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **openvino:** implement voice style foundation and orchestration layer ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **openvino:** implement voice style foundation and orchestration layer ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **openvino:** implement voice style foundation and orchestration layer ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **openvino:** implement voice style foundation and orchestration layer ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **openvino:** implement voice style foundation and orchestration layer ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **openvino:** implement voice style foundation and orchestration layer ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **openvino:** implement voice style foundation and orchestration layer ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **openvino:** implement voice style foundation and orchestration layer ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **openvino:** implement voice style foundation and orchestration layer ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **openvino:** implement voice style foundation and orchestration layer ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **openvino:** implement voice style foundation and orchestration layer ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **openvino:** implement voice style foundation and orchestration layer ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **openvino:** implement voice style foundation and orchestration layer ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **openvino:** implement voice style foundation and orchestration layer ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **openvino:** implement voice style foundation and orchestration layer ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **openvino:** implement voice style foundation and orchestration layer ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **openvino:** implement voice style foundation and orchestration layer ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **openvino:** implement voice style foundation and orchestration layer ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **openvino:** implement voice style foundation and orchestration layer ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **openvino:** implement voice style foundation and orchestration layer ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **openvino:** implement voice style foundation and orchestration layer ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **openvino:** implement voice style foundation and orchestration layer ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **openvino:** implement voice style foundation and orchestration layer ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **openvino:** implement voice style foundation and orchestration layer ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **openvino:** implement voice style foundation and orchestration layer ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **openvino:** implement voice style foundation and orchestration layer ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **openvino:** implement voice style foundation and orchestration layer ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **openvino:** implement voice style foundation and orchestration layer ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **openvino:** implement voice style foundation and orchestration layer ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **openvino:** implement voice style foundation and orchestration layer ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **openvino:** implement voice style foundation and orchestration layer ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **openvino:** implement voice style foundation and orchestration layer ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **openvino:** implement voice style foundation and orchestration layer ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **openvino:** implement voice style foundation and orchestration layer ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **openvino:** implement voice style foundation and orchestration layer ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **openvino:** implement voice style foundation and orchestration layer ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **openvino:** implement voice style foundation and orchestration layer ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **openvino:** implement voice style foundation and orchestration layer ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **openvino:** implement voice style foundation and orchestration layer ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **openvino:** implement voice style foundation and orchestration layer ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **openvino:** implement voice style foundation and orchestration layer ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **openvino:** implement voice style foundation and orchestration layer ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **openvino:** implement voice style foundation and orchestration layer ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **openvino:** implement voice style foundation and orchestration layer ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **openvino:** implement voice style foundation and orchestration layer ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **openvino:** implement voice style foundation and orchestration layer ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **openvino:** implement voice style foundation and orchestration layer ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **openvino:** implement voice style foundation and orchestration layer ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **openvino:** implement voice style foundation and orchestration layer ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **openvino:** implement voice style foundation and orchestration layer ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **openvino:** implement voice style foundation and orchestration layer ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **openvino:** implement voice style foundation and orchestration layer ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **openvino:** implement voice style foundation and orchestration layer ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **openvino:** implement voice style foundation and orchestration layer ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **openvino:** implement voice style foundation and orchestration layer ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **openvino:** implement voice style foundation and orchestration layer ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **openvino:** implement voice style foundation and orchestration layer ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **openvino:** implement voice style foundation and orchestration layer ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **openvino:** implement voice style foundation and orchestration layer ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **openvino:** implement voice style foundation and orchestration layer ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **openvino:** implement voice style foundation and orchestration layer ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **openvino:** implement voice style foundation and orchestration layer ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **openvino:** implement voice style foundation and orchestration layer ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **openvino:** implement voice style foundation and orchestration layer ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **openvino:** implement voice style foundation and orchestration layer ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **openvino:** implement voice style foundation and orchestration layer ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **openvino:** implement voice style foundation and orchestration layer ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **openvino:** implement voice style foundation and orchestration layer ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **openvino:** implement voice style foundation and orchestration layer ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **openvino:** implement voice style foundation and orchestration layer ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **openvino:** implement voice style foundation and orchestration layer ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **openvino:** implement voice style foundation and orchestration layer ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **openvino:** implement voice style foundation and orchestration layer ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **openvino:** implement voice style foundation and orchestration layer ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **openvino:** implement voice style foundation and orchestration layer ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **openvino:** implement voice style foundation and orchestration layer ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **openvino:** implement voice style foundation and orchestration layer ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **openvino:** implement voice style foundation and orchestration layer ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **openvino:** implement voice style foundation and orchestration layer ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **openvino:** implement voice style foundation and orchestration layer ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **openvino:** implement voice style foundation and orchestration layer ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **openvino:** implement voice style foundation and orchestration layer ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **openvino:** implement voice style foundation and orchestration layer ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **openvino:** implement voice style foundation and orchestration layer ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **openvino:** implement voice style foundation and orchestration layer ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **openvino:** implement voice style foundation and orchestration layer ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **openvino:** implement voice style foundation and orchestration layer ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **openvino:** implement voice style foundation and orchestration layer ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **openvino:** implement voice style foundation and orchestration layer ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **openvino:** implement voice style foundation and orchestration layer ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **openvino:** implement voice style foundation and orchestration layer ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **openvino:** implement voice style foundation and orchestration layer ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **openvino:** implement voice style foundation and orchestration layer ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **openvino:** implement voice style foundation and orchestration layer ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **openvino:** implement voice style foundation and orchestration layer ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **openvino:** implement voice style foundation and orchestration layer ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **openvino:** implement voice style foundation and orchestration layer ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **openvino:** implement voice style foundation and orchestration layer ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **openvino:** implement voice style foundation and orchestration layer ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **openvino:** implement voice style foundation and orchestration layer ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **openvino:** implement voice style foundation and orchestration layer ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **openvino:** implement voice style foundation and orchestration layer ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **openvino:** implement voice style foundation and orchestration layer ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **openvino:** implement voice style foundation and orchestration layer ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **prosody:** implement forced-alignment engine, cache, and async processing ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **prosody:** implement forced-alignment engine, cache, and async processing ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **prosody:** implement forced-alignment engine, cache, and async processing ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **prosody:** implement forced-alignment engine, cache, and async processing ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **prosody:** implement forced-alignment engine, cache, and async processing ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **prosody:** implement forced-alignment engine, cache, and async processing ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **prosody:** implement forced-alignment engine, cache, and async processing ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **prosody:** implement forced-alignment engine, cache, and async processing ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **prosody:** implement forced-alignment engine, cache, and async processing ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **prosody:** implement forced-alignment engine, cache, and async processing ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **prosody:** implement forced-alignment engine, cache, and async processing ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **prosody:** implement forced-alignment engine, cache, and async processing ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **prosody:** implement forced-alignment engine, cache, and async processing ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **prosody:** implement forced-alignment engine, cache, and async processing ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **prosody:** implement forced-alignment engine, cache, and async processing ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **prosody:** implement forced-alignment engine, cache, and async processing ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **prosody:** implement forced-alignment engine, cache, and async processing ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **prosody:** implement forced-alignment engine, cache, and async processing ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **prosody:** implement forced-alignment engine, cache, and async processing ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **prosody:** implement forced-alignment engine, cache, and async processing ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **prosody:** implement forced-alignment engine, cache, and async processing ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **prosody:** implement forced-alignment engine, cache, and async processing ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **prosody:** implement forced-alignment engine, cache, and async processing ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **prosody:** implement forced-alignment engine, cache, and async processing ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **prosody:** implement forced-alignment engine, cache, and async processing ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **prosody:** implement forced-alignment engine, cache, and async processing ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **prosody:** implement forced-alignment engine, cache, and async processing ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **prosody:** implement forced-alignment engine, cache, and async processing ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **prosody:** implement forced-alignment engine, cache, and async processing ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **prosody:** implement forced-alignment engine, cache, and async processing ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **prosody:** implement forced-alignment engine, cache, and async processing ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **prosody:** implement forced-alignment engine, cache, and async processing ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **prosody:** implement forced-alignment engine, cache, and async processing ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **prosody:** implement forced-alignment engine, cache, and async processing ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **prosody:** implement forced-alignment engine, cache, and async processing ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **prosody:** implement forced-alignment engine, cache, and async processing ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **prosody:** implement forced-alignment engine, cache, and async processing ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **prosody:** implement forced-alignment engine, cache, and async processing ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **prosody:** implement forced-alignment engine, cache, and async processing ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **prosody:** implement forced-alignment engine, cache, and async processing ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **prosody:** implement forced-alignment engine, cache, and async processing ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **prosody:** implement forced-alignment engine, cache, and async processing ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **prosody:** implement forced-alignment engine, cache, and async processing ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **prosody:** implement forced-alignment engine, cache, and async processing ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **prosody:** implement forced-alignment engine, cache, and async processing ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **prosody:** implement forced-alignment engine, cache, and async processing ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **prosody:** implement forced-alignment engine, cache, and async processing ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **prosody:** implement forced-alignment engine, cache, and async processing ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **prosody:** implement forced-alignment engine, cache, and async processing ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **prosody:** implement forced-alignment engine, cache, and async processing ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **prosody:** implement forced-alignment engine, cache, and async processing ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **prosody:** implement forced-alignment engine, cache, and async processing ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **prosody:** implement forced-alignment engine, cache, and async processing ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **prosody:** implement forced-alignment engine, cache, and async processing ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **prosody:** implement forced-alignment engine, cache, and async processing ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **prosody:** implement forced-alignment engine, cache, and async processing ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **prosody:** implement forced-alignment engine, cache, and async processing ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **prosody:** implement forced-alignment engine, cache, and async processing ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **prosody:** implement forced-alignment engine, cache, and async processing ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **prosody:** implement forced-alignment engine, cache, and async processing ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **prosody:** implement forced-alignment engine, cache, and async processing ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **prosody:** implement forced-alignment engine, cache, and async processing ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **prosody:** implement forced-alignment engine, cache, and async processing ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **prosody:** implement forced-alignment engine, cache, and async processing ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **prosody:** implement forced-alignment engine, cache, and async processing ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **prosody:** implement forced-alignment engine, cache, and async processing ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **prosody:** implement forced-alignment engine, cache, and async processing ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **prosody:** implement forced-alignment engine, cache, and async processing ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **prosody:** implement forced-alignment engine, cache, and async processing ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **prosody:** implement forced-alignment engine, cache, and async processing ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **prosody:** implement forced-alignment engine, cache, and async processing ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **prosody:** implement forced-alignment engine, cache, and async processing ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **prosody:** implement forced-alignment engine, cache, and async processing ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **prosody:** implement forced-alignment engine, cache, and async processing ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **prosody:** implement forced-alignment engine, cache, and async processing ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **prosody:** implement forced-alignment engine, cache, and async processing ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **prosody:** implement forced-alignment engine, cache, and async processing ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **prosody:** implement forced-alignment engine, cache, and async processing ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **prosody:** implement forced-alignment engine, cache, and async processing ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **prosody:** implement forced-alignment engine, cache, and async processing ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **prosody:** implement forced-alignment engine, cache, and async processing ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **prosody:** implement forced-alignment engine, cache, and async processing ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **prosody:** implement forced-alignment engine, cache, and async processing ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **prosody:** implement forced-alignment engine, cache, and async processing ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **prosody:** implement forced-alignment engine, cache, and async processing ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **prosody:** implement forced-alignment engine, cache, and async processing ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **prosody:** implement forced-alignment engine, cache, and async processing ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **prosody:** implement forced-alignment engine, cache, and async processing ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **prosody:** implement forced-alignment engine, cache, and async processing ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **prosody:** implement forced-alignment engine, cache, and async processing ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **prosody:** implement forced-alignment engine, cache, and async processing ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **prosody:** implement forced-alignment engine, cache, and async processing ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **prosody:** implement forced-alignment engine, cache, and async processing ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **prosody:** implement forced-alignment engine, cache, and async processing ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **prosody:** implement forced-alignment engine, cache, and async processing ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **prosody:** implement forced-alignment engine, cache, and async processing ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **prosody:** implement forced-alignment engine, cache, and async processing ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **prosody:** implement forced-alignment engine, cache, and async processing ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **prosody:** implement forced-alignment engine, cache, and async processing ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **prosody:** implement forced-alignment engine, cache, and async processing ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **prosody:** implement forced-alignment engine, cache, and async processing ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **prosody:** implement forced-alignment engine, cache, and async processing ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **prosody:** implement forced-alignment engine, cache, and async processing ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **prosody:** implement forced-alignment engine, cache, and async processing ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **prosody:** implement forced-alignment engine, cache, and async processing ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **prosody:** implement forced-alignment engine, cache, and async processing ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **prosody:** implement forced-alignment engine, cache, and async processing ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **prosody:** implement forced-alignment engine, cache, and async processing ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **prosody:** implement forced-alignment engine, cache, and async processing ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **prosody:** implement forced-alignment engine, cache, and async processing ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **prosody:** implement forced-alignment engine, cache, and async processing ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **prosody:** implement forced-alignment engine, cache, and async processing ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **prosody:** implement forced-alignment engine, cache, and async processing ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **prosody:** implement forced-alignment engine, cache, and async processing ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **prosody:** implement forced-alignment engine, cache, and async processing ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **prosody:** implement forced-alignment engine, cache, and async processing ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **prosody:** implement forced-alignment engine, cache, and async processing ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **prosody:** implement forced-alignment engine, cache, and async processing ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **prosody:** implement forced-alignment engine, cache, and async processing ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **prosody:** implement forced-alignment engine, cache, and async processing ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **prosody:** implement forced-alignment engine, cache, and async processing ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **prosody:** implement forced-alignment engine, cache, and async processing ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **prosody:** implement forced-alignment engine, cache, and async processing ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **runtime:** add decode-step heartbeat in OVStatefulCore ([5ea00db](https://github.com/nmorgowicz-org/persona-forge/commit/5ea00dbde2592d27a6d3682b9b776a1810855c0d))
* **runtime:** add EOS conditioning fix, step-level diagnostics, and free-run handoff ([2092df3](https://github.com/nmorgowicz-org/persona-forge/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))
* **runtime:** add M4 OpenVINO talker runtime with explicit K/V cache, persistent InferRequests ([e9d9943](https://github.com/nmorgowicz-org/persona-forge/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **runtime:** add MODEL_DTYPE control with backend-aware safety and bf16→float32 auto-correction on swap ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** add mount health checks (REF_AUDIO, /voices, /segments, HF cache, OV dir) and /health mount/pocket_tts reporting ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** add run_bench.sh for simpler harness invocation ([0e3d13c](https://github.com/nmorgowicz-org/persona-forge/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))
* **runtime:** add stateful KV cache support for the 0.6B main and predictor cores ([7a7b091](https://github.com/nmorgowicz-org/persona-forge/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **runtime:** add TTS_MAX_NEW_TOKENS cap, TTS_NON_STREAMING override, and prompt diagnostics ([2092df3](https://github.com/nmorgowicz-org/persona-forge/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))
* **runtime:** async OmniVoice job queueing when model is not yet loaded ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **runtime:** expose OV_INFERENCE_THREADS; wire torch.set_num_threads to it ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** identical-seed batch vs streaming latency comparison ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **runtime:** idle model unload with configurable cooldown and RAM telemetry ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** implement bounded generation for prosody repair ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **runtime:** implement bounded generation for prosody repair ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **runtime:** implement bounded generation for prosody repair ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **runtime:** implement bounded generation for prosody repair ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **runtime:** implement bounded generation for prosody repair ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **runtime:** implement bounded generation for prosody repair ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **runtime:** implement bounded generation for prosody repair ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **runtime:** implement bounded generation for prosody repair ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **runtime:** implement bounded generation for prosody repair ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **runtime:** implement bounded generation for prosody repair ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **runtime:** implement bounded generation for prosody repair ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **runtime:** implement bounded generation for prosody repair ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **runtime:** implement bounded generation for prosody repair ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **runtime:** implement bounded generation for prosody repair ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **runtime:** implement bounded generation for prosody repair ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **runtime:** implement bounded generation for prosody repair ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **runtime:** implement bounded generation for prosody repair ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **runtime:** implement bounded generation for prosody repair ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **runtime:** implement bounded generation for prosody repair ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **runtime:** implement bounded generation for prosody repair ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **runtime:** implement bounded generation for prosody repair ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **runtime:** implement bounded generation for prosody repair ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **runtime:** implement bounded generation for prosody repair ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **runtime:** implement bounded generation for prosody repair ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **runtime:** implement bounded generation for prosody repair ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **runtime:** implement bounded generation for prosody repair ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **runtime:** implement bounded generation for prosody repair ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **runtime:** implement bounded generation for prosody repair ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **runtime:** implement bounded generation for prosody repair ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **runtime:** implement bounded generation for prosody repair ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **runtime:** implement bounded generation for prosody repair ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **runtime:** implement bounded generation for prosody repair ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **runtime:** implement bounded generation for prosody repair ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **runtime:** implement bounded generation for prosody repair ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **runtime:** implement bounded generation for prosody repair ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **runtime:** implement bounded generation for prosody repair ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **runtime:** implement bounded generation for prosody repair ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **runtime:** implement bounded generation for prosody repair ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **runtime:** implement bounded generation for prosody repair ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **runtime:** implement bounded generation for prosody repair ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **runtime:** implement bounded generation for prosody repair ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **runtime:** implement bounded generation for prosody repair ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **runtime:** implement bounded generation for prosody repair ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **runtime:** implement bounded generation for prosody repair ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **runtime:** implement bounded generation for prosody repair ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **runtime:** implement bounded generation for prosody repair ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **runtime:** implement bounded generation for prosody repair ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **runtime:** implement bounded generation for prosody repair ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **runtime:** implement bounded generation for prosody repair ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **runtime:** implement bounded generation for prosody repair ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **runtime:** implement bounded generation for prosody repair ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **runtime:** implement bounded generation for prosody repair ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **runtime:** implement bounded generation for prosody repair ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **runtime:** implement bounded generation for prosody repair ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **runtime:** implement bounded generation for prosody repair ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **runtime:** implement bounded generation for prosody repair ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **runtime:** implement bounded generation for prosody repair ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **runtime:** implement bounded generation for prosody repair ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **runtime:** implement bounded generation for prosody repair ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **runtime:** implement bounded generation for prosody repair ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **runtime:** implement bounded generation for prosody repair ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **runtime:** implement bounded generation for prosody repair ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **runtime:** implement bounded generation for prosody repair ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **runtime:** implement bounded generation for prosody repair ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **runtime:** implement bounded generation for prosody repair ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **runtime:** implement bounded generation for prosody repair ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **runtime:** implement bounded generation for prosody repair ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **runtime:** implement bounded generation for prosody repair ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **runtime:** implement bounded generation for prosody repair ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **runtime:** implement bounded generation for prosody repair ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **runtime:** implement bounded generation for prosody repair ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **runtime:** implement bounded generation for prosody repair ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **runtime:** implement bounded generation for prosody repair ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **runtime:** implement bounded generation for prosody repair ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **runtime:** implement bounded generation for prosody repair ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **runtime:** implement bounded generation for prosody repair ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **runtime:** implement bounded generation for prosody repair ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **runtime:** implement bounded generation for prosody repair ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **runtime:** implement bounded generation for prosody repair ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **runtime:** implement bounded generation for prosody repair ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **runtime:** implement bounded generation for prosody repair ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **runtime:** implement bounded generation for prosody repair ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **runtime:** implement bounded generation for prosody repair ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **runtime:** implement bounded generation for prosody repair ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **runtime:** implement bounded generation for prosody repair ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **runtime:** implement bounded generation for prosody repair ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **runtime:** implement bounded generation for prosody repair ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **runtime:** implement bounded generation for prosody repair ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **runtime:** implement bounded generation for prosody repair ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **runtime:** implement bounded generation for prosody repair ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **runtime:** implement bounded generation for prosody repair ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **runtime:** implement bounded generation for prosody repair ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **runtime:** implement bounded generation for prosody repair ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **runtime:** implement bounded generation for prosody repair ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **runtime:** implement bounded generation for prosody repair ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **runtime:** implement bounded generation for prosody repair ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **runtime:** implement bounded generation for prosody repair ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **runtime:** implement bounded generation for prosody repair ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **runtime:** implement bounded generation for prosody repair ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **runtime:** implement bounded generation for prosody repair ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **runtime:** implement bounded generation for prosody repair ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **runtime:** implement bounded generation for prosody repair ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **runtime:** implement bounded generation for prosody repair ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **runtime:** implement bounded generation for prosody repair ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **runtime:** implement bounded generation for prosody repair ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **runtime:** implement bounded generation for prosody repair ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **runtime:** implement bounded generation for prosody repair ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **runtime:** implement bounded generation for prosody repair ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **runtime:** implement bounded generation for prosody repair ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **runtime:** implement bounded generation for prosody repair ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **runtime:** implement bounded generation for prosody repair ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **runtime:** implement bounded generation for prosody repair ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **runtime:** implement bounded generation for prosody repair ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **runtime:** implement bounded generation for prosody repair ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **runtime:** implement bounded generation for prosody repair ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **runtime:** implement bounded generation for prosody repair ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **runtime:** implement bounded generation for prosody repair ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **runtime:** implement bounded generation for prosody repair ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **runtime:** implement bounded generation for prosody repair ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **runtime:** implement bounded generation for prosody repair ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **runtime:** implement bounded generation for prosody repair ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **runtime:** implement bounded generation for prosody repair ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **runtime:** implement bounded generation for prosody repair ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **runtime:** implement voice library backend and configuration ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **runtime:** implement voice library backend and configuration ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **runtime:** implement voice library backend and configuration ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **runtime:** implement voice library backend and configuration ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **runtime:** implement voice library backend and configuration ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **runtime:** implement voice library backend and configuration ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **runtime:** implement voice library backend and configuration ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **runtime:** implement voice library backend and configuration ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **runtime:** implement voice library backend and configuration ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **runtime:** implement voice library backend and configuration ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **runtime:** implement voice library backend and configuration ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **runtime:** implement voice library backend and configuration ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **runtime:** implement voice library backend and configuration ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **runtime:** implement voice library backend and configuration ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **runtime:** implement voice library backend and configuration ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **runtime:** implement voice library backend and configuration ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **runtime:** implement voice library backend and configuration ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **runtime:** implement voice library backend and configuration ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **runtime:** implement voice library backend and configuration ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **runtime:** implement voice library backend and configuration ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **runtime:** implement voice library backend and configuration ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **runtime:** implement voice library backend and configuration ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **runtime:** implement voice library backend and configuration ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **runtime:** implement voice library backend and configuration ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **runtime:** implement voice library backend and configuration ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **runtime:** implement voice library backend and configuration ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **runtime:** implement voice library backend and configuration ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **runtime:** implement voice library backend and configuration ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **runtime:** implement voice library backend and configuration ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **runtime:** implement voice library backend and configuration ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **runtime:** implement voice library backend and configuration ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **runtime:** implement voice library backend and configuration ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **runtime:** implement voice library backend and configuration ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **runtime:** implement voice library backend and configuration ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **runtime:** implement voice library backend and configuration ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **runtime:** implement voice library backend and configuration ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **runtime:** implement voice library backend and configuration ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **runtime:** implement voice library backend and configuration ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **runtime:** implement voice library backend and configuration ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **runtime:** implement voice library backend and configuration ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **runtime:** implement voice library backend and configuration ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **runtime:** implement voice library backend and configuration ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **runtime:** implement voice library backend and configuration ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **runtime:** implement voice library backend and configuration ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **runtime:** implement voice library backend and configuration ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **runtime:** implement voice library backend and configuration ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **runtime:** implement voice library backend and configuration ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **runtime:** implement voice library backend and configuration ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **runtime:** implement voice library backend and configuration ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **runtime:** implement voice library backend and configuration ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **runtime:** implement voice library backend and configuration ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **runtime:** implement voice library backend and configuration ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **runtime:** implement voice library backend and configuration ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **runtime:** implement voice library backend and configuration ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **runtime:** implement voice library backend and configuration ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **runtime:** implement voice library backend and configuration ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **runtime:** implement voice library backend and configuration ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **runtime:** implement voice library backend and configuration ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **runtime:** implement voice library backend and configuration ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **runtime:** implement voice library backend and configuration ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **runtime:** implement voice library backend and configuration ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **runtime:** implement voice library backend and configuration ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **runtime:** implement voice library backend and configuration ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **runtime:** implement voice library backend and configuration ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **runtime:** implement voice library backend and configuration ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **runtime:** implement voice library backend and configuration ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **runtime:** implement voice library backend and configuration ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **runtime:** implement voice library backend and configuration ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **runtime:** implement voice library backend and configuration ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **runtime:** implement voice library backend and configuration ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **runtime:** implement voice library backend and configuration ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **runtime:** implement voice library backend and configuration ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **runtime:** implement voice library backend and configuration ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **runtime:** implement voice library backend and configuration ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **runtime:** implement voice library backend and configuration ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **runtime:** implement voice library backend and configuration ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **runtime:** implement voice library backend and configuration ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **runtime:** implement voice library backend and configuration ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **runtime:** implement voice library backend and configuration ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **runtime:** implement voice library backend and configuration ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **runtime:** implement voice library backend and configuration ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **runtime:** implement voice library backend and configuration ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **runtime:** implement voice library backend and configuration ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **runtime:** implement voice library backend and configuration ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **runtime:** implement voice library backend and configuration ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **runtime:** implement voice library backend and configuration ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **runtime:** implement voice library backend and configuration ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **runtime:** implement voice library backend and configuration ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **runtime:** implement voice library backend and configuration ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **runtime:** implement voice library backend and configuration ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **runtime:** implement voice library backend and configuration ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **runtime:** implement voice library backend and configuration ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **runtime:** implement voice library backend and configuration ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **runtime:** implement voice library backend and configuration ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **runtime:** implement voice library backend and configuration ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **runtime:** implement voice library backend and configuration ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **runtime:** implement voice library backend and configuration ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **runtime:** implement voice library backend and configuration ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **runtime:** implement voice library backend and configuration ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **runtime:** implement voice library backend and configuration ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **runtime:** implement voice library backend and configuration ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **runtime:** implement voice library backend and configuration ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **runtime:** implement voice library backend and configuration ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **runtime:** implement voice library backend and configuration ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **runtime:** implement voice library backend and configuration ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **runtime:** implement voice library backend and configuration ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **runtime:** implement voice library backend and configuration ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **runtime:** implement voice library backend and configuration ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **runtime:** implement voice library backend and configuration ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **runtime:** implement voice library backend and configuration ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **runtime:** implement voice library backend and configuration ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **runtime:** implement voice library backend and configuration ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **runtime:** implement voice library backend and configuration ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **runtime:** implement voice library backend and configuration ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **runtime:** implement voice library backend and configuration ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **runtime:** implement voice library backend and configuration ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **runtime:** implement voice library backend and configuration ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **runtime:** implement voice library backend and configuration ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **runtime:** implement voice library backend and configuration ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **runtime:** implement voice library backend and configuration ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **runtime:** implement voice library backend and configuration ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **runtime:** implement voice library backend and configuration ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **runtime:** implement voice library backend and configuration ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **runtime:** improve test_ov_generation.py reporting and output path safety ([0e3d13c](https://github.com/nmorgowicz-org/persona-forge/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))
* **runtime:** integrate Pocket TTS as hotswappable backend with generation, voice states, and live knobs ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** load Base model in background; allow /generate to queue through swaps instead of 503ing ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **runtime:** log generation start, elapsed time, audio duration, and RTF ([8a65186](https://github.com/nmorgowicz-org/persona-forge/commit/8a6518691249cfccce0891ef70125400234d783b))
* **runtime:** OpenVINO compiled kernel cache via OV_CACHE_DIR ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** register mounted REF_AUDIO as first-class "Mounted reference" voice; show "Mounted" badge in VoiceSelector ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** release PyTorch codec after startup to cut ~0.4 GiB RSS ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **runtime:** release PyTorch core weights post-install (M7 memory) ([679799d](https://github.com/nmorgowicz-org/persona-forge/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **runtime:** stream OpenVINO vocoder PCM during generation ([d67a505](https://github.com/nmorgowicz-org/persona-forge/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))
* **runtime:** unify TTS_DIAG across backends and add watchdog with hard timeout; tighter pytorch+bf16 token cap; opt-in bf16→float32 auto-fallback ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** wire INT8 tuning, parity gates, and TTS_BACKEND selection ([2ecf8e3](https://github.com/nmorgowicz-org/persona-forge/commit/2ecf8e3ddc3d28aff99de9aa7a8679c75b253eb8))
* **test:** add generation-level parity harness (code agreement, waveform SNR, latency/RTF) ([e9d9943](https://github.com/nmorgowicz-org/persona-forge/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **tests:** add Playwright E2E suite, screenshot harness, and dedicated UI CI workflow ([1d56671](https://github.com/nmorgowicz-org/persona-forge/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))


### Bug Fixes

* **ci:** add .release-please-manifest.json required by release-please v17 ([#2](https://github.com/nmorgowicz-org/persona-forge/issues/2)) ([97c3bee](https://github.com/nmorgowicz-org/persona-forge/commit/97c3bee81b99f284c369008a6ee2c930a39ad078))
* **ci:** add no-cache dispatch input to recover from broken GHCR build cache ([e68eb16](https://github.com/nmorgowicz-org/persona-forge/commit/e68eb1679a566c4a7a2d5eca706103484d77bb6f))
* **ci:** authenticate and reduce Docker Hub pulls in image validation ([b320f0d](https://github.com/nmorgowicz-org/persona-forge/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))
* **ci:** broaden ignore-versions to protect all runtime/exporter/buildcache tags ([5340067](https://github.com/nmorgowicz-org/persona-forge/commit/5340067f52f012a87a8498499c593c7ab634526f))
* **ci:** correct release-please-action v4.4.1 SHA ([e6fc11f](https://github.com/nmorgowicz-org/persona-forge/commit/e6fc11f2d0eb37ab196dd28670db863a6161175b))
* **ci:** correct release-please-action v4.4.1 SHA ([4e966bf](https://github.com/nmorgowicz-org/persona-forge/commit/4e966bfb8e59343efcd28da5fb445ca48b7ad090))
* **ci:** install NumPy for dump-audio unit tests ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **ci:** make Dockerfile COPY-line check robust to additional files ([5717ddb](https://github.com/nmorgowicz-org/persona-forge/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))
* **ci:** pin release-please to v4.4.1 (no parser bug), use rust release-type ([43e2d1b](https://github.com/nmorgowicz-org/persona-forge/commit/43e2d1bb3bc7b7c193c73ce10612044f3cbe9691))
* **ci:** publish images only from Release Please tags ([bec5163](https://github.com/nmorgowicz-org/persona-forge/commit/bec516367a4a31a778a6ffcb744d7c50e028f69d))
* **ci:** publish one complete container image ([b7defd7](https://github.com/nmorgowicz-org/persona-forge/commit/b7defd7be16c6817713c162b88181fb3b77611b2))
* **ci:** remove unsupported pull-request-header and align version to 0.2.0 ([bf3578e](https://github.com/nmorgowicz-org/persona-forge/commit/bf3578ef7929477249a1c80e65d90e36c4548664))
* **ci:** restore original release-please workflow (remove permission overrides, v5.0.0) ([760acda](https://github.com/nmorgowicz-org/persona-forge/commit/760acda24978dddb85c8be9ccf14bd0f4dc6d440))
* **ci:** restore release-please parsing and latest action ([de12867](https://github.com/nmorgowicz-org/persona-forge/commit/de128675154a3240735cb45651f6af5e63fe89f1))
* **ci:** retain reliable GHCR cleanup with 15 versions ([b320f0d](https://github.com/nmorgowicz-org/persona-forge/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))
* **ci:** specify explicit permissions for release-please GitHub App token ([92a6745](https://github.com/nmorgowicz-org/persona-forge/commit/92a674560e609355df3266d7059bd50e9a0fab2d))
* **ci:** specify explicit permissions for release-please GitHub App token ([#112](https://github.com/nmorgowicz-org/persona-forge/issues/112)) ([627fb11](https://github.com/nmorgowicz-org/persona-forge/commit/627fb11fe8835c39c880f09daa32e45e91868464))
* **ci:** tag-aware GHCR cleanup preserves protected image versions ([95ca024](https://github.com/nmorgowicz-org/persona-forge/commit/95ca024267415ed1688758b9cdce664f9bbfb207))
* **ci:** use correct permission- prefix for release-please App token ([c08a6e6](https://github.com/nmorgowicz-org/persona-forge/commit/c08a6e62c041167198d588c8f70d7525b29b6eb8))
* **ci:** use correct permission- prefix for release-please App token ([d9b6f07](https://github.com/nmorgowicz-org/persona-forge/commit/d9b6f07acdf2612504ace26bc4043e23c2153d50))
* **ci:** use curl instead of gh in GHCR cleanup (gh not installed on runner) ([794df6c](https://github.com/nmorgowicz-org/persona-forge/commit/794df6cd390b5577a34a1b07ec6f0a03c0e9c5e3))
* **ci:** use node release-type for proper Conventional Commits parsing ([7807741](https://github.com/nmorgowicz-org/persona-forge/commit/780774105b9d6da9409171161f6a168493c2345e))
* **ci:** use rust release-type like llama-monitor to avoid release creation error ([6cef070](https://github.com/nmorgowicz-org/persona-forge/commit/6cef070450dcaed60209494eedb270519c7065ee))
* **ci:** use simple release-type (not rust) for Python project ([cf6a219](https://github.com/nmorgowicz-org/persona-forge/commit/cf6a219d23ce3302b70fb2752b09dafa1369a8f8))
* **compose:** default MODEL_SIZE to 1.7B to match recommendation ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **deps:** add sox Python package to runtime deps ([8262bbd](https://github.com/nmorgowicz-org/persona-forge/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** patch qwen-tts check_model_inputs for transformers 5.x API ([8262bbd](https://github.com/nmorgowicz-org/persona-forge/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** patch qwen-tts pad_token_id access for transformers 5.x ([8a65186](https://github.com/nmorgowicz-org/persona-forge/commit/8a6518691249cfccce0891ef70125400234d783b))
* **deps:** patch qwen-tts pad_token_id access for transformers 5.x ([aa33890](https://github.com/nmorgowicz-org/persona-forge/commit/aa33890aef859c7324bb821d42823576901fb9b0))
* **deps:** remove check_model_inputs decorator instead of replacing it ([8262bbd](https://github.com/nmorgowicz-org/persona-forge/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** remove qwen-tts from runtime.txt to resolve pip conflict ([8262bbd](https://github.com/nmorgowicz-org/persona-forge/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** rename requirements manifests for Dependabot graph compatibility ([9db3930](https://github.com/nmorgowicz-org/persona-forge/commit/9db39308fd012e52e41cbf4cae73632d71184c0d))
* **deps:** restore 'default' RoPE type removed in transformers 5.x ([d5f3ad5](https://github.com/nmorgowicz-org/persona-forge/commit/d5f3ad5ff036d6bf6ef9e5898fea7930b8db5335))
* **deps:** restore 'default' RoPE type removed in transformers 5.x ([10c8a0c](https://github.com/nmorgowicz-org/persona-forge/commit/10c8a0c33f63a8394c7f74c69192e5c590a90445))
* **deps:** upgrade transformers to 5.12.1 to fix CVE-2026-1839 ([8262bbd](https://github.com/nmorgowicz-org/persona-forge/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **docker:** include ov_runtime_config, ov_talker_runtime, bench_common, test_ov_generation in build ([5717ddb](https://github.com/nmorgowicz-org/persona-forge/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))
* drop cache_position from create_causal_mask for transformers 5.x ([b8901c9](https://github.com/nmorgowicz-org/persona-forge/commit/b8901c9646a9554e86df793911d5efdf0b4c0ccc))
* **export:** correct INT8 mode selection and make transformer parity fail closed ([b320f0d](https://github.com/nmorgowicz-org/persona-forge/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))
* **export:** include the OpenVINO export CLI in the exporter image ([bec5163](https://github.com/nmorgowicz-org/persona-forge/commit/bec516367a4a31a778a6ffcb744d7c50e028f69d))
* **export:** patch DynamicLayer.lazy_initialization to fix OV aten::cat rank error ([aebce00](https://github.com/nmorgowicz-org/persona-forge/commit/aebce0047693a92202a5c6b9bcf312db73736ee0))
* **export:** pre-build 4D causal mask to prevent static kv_length in decode IR ([#16](https://github.com/nmorgowicz-org/persona-forge/issues/16)) ([10b2260](https://github.com/nmorgowicz-org/persona-forge/commit/10b2260a6a7371ee20aca9926124d45622fb8eda))
* **export:** reject unsupported INT8 calibration ([08e1c58](https://github.com/nmorgowicz-org/persona-forge/commit/08e1c58c0413596fa10d75ffb6a435ede4021662))
* **export:** require SOURCE_COMMIT and EXPORTER_IMAGE_DIGEST provenance env vars ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** resolve loaded vocoder decoder access path ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** respect NNCF INT8 constraints (no group_size/ratio overrides) ([0d7ce4f](https://github.com/nmorgowicz-org/persona-forge/commit/0d7ce4f90b67eb58a063827f87fa14c813806731))
* **export:** supply traceable causal and sliding-window attention masks ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** trace with eager attention on nested configs ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** use fixed 325-frame vocoder input contract ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** use rank-4 empty tensor in DynamicLayer to fix OV aten::cat rejection ([5340067](https://github.com/nmorgowicz-org/persona-forge/commit/5340067f52f012a87a8498499c593c7ab634526f))
* fix Dockerfile indentation for input_embeds patch ([3bf171f](https://github.com/nmorgowicz-org/persona-forge/commit/3bf171f1508f84c50ecf0c53b3aa70e180f65f0b))
* **frontend:** bound /health swap-status polling with timeout and exponential backoff ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **harness:** correct frame/codebook axes in M4 code comparison ([d7136c4](https://github.com/nmorgowicz-org/persona-forge/commit/d7136c4c4ef99f5cbe762ecad6879db0ede9ccc5))
* **m9:** clean up _OVStatefulCore delegation and accept generation_steps ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** fail-closed startup when OPENVINO_RELEASE_TORCH=1 ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **model:** correct reference silence trimming logic ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **model:** correct reference silence trimming logic ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **model:** correct reference silence trimming logic ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **model:** correct reference silence trimming logic ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **model:** correct reference silence trimming logic ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **model:** correct reference silence trimming logic ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **model:** correct reference silence trimming logic ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **model:** correct reference silence trimming logic ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **model:** correct reference silence trimming logic ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **model:** correct reference silence trimming logic ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **model:** correct reference silence trimming logic ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **model:** correct reference silence trimming logic ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **model:** correct reference silence trimming logic ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **model:** correct reference silence trimming logic ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **model:** correct reference silence trimming logic ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **model:** correct reference silence trimming logic ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **model:** correct reference silence trimming logic ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **model:** correct reference silence trimming logic ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **model:** correct reference silence trimming logic ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **model:** correct reference silence trimming logic ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **model:** correct reference silence trimming logic ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **model:** correct reference silence trimming logic ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **model:** correct reference silence trimming logic ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **model:** correct reference silence trimming logic ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **model:** correct reference silence trimming logic ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **model:** correct reference silence trimming logic ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **model:** correct reference silence trimming logic ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **model:** correct reference silence trimming logic ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **model:** correct reference silence trimming logic ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **model:** correct reference silence trimming logic ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **model:** correct reference silence trimming logic ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **model:** correct reference silence trimming logic ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **model:** correct reference silence trimming logic ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **model:** correct reference silence trimming logic ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **model:** correct reference silence trimming logic ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **model:** correct reference silence trimming logic ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **model:** correct reference silence trimming logic ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **model:** correct reference silence trimming logic ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **model:** correct reference silence trimming logic ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **model:** correct reference silence trimming logic ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **model:** correct reference silence trimming logic ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **model:** correct reference silence trimming logic ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **model:** correct reference silence trimming logic ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **model:** correct reference silence trimming logic ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **model:** correct reference silence trimming logic ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **model:** correct reference silence trimming logic ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **model:** correct reference silence trimming logic ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **model:** correct reference silence trimming logic ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **model:** correct reference silence trimming logic ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **model:** correct reference silence trimming logic ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **model:** correct reference silence trimming logic ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **model:** correct reference silence trimming logic ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **model:** correct reference silence trimming logic ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **model:** correct reference silence trimming logic ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **model:** correct reference silence trimming logic ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **model:** correct reference silence trimming logic ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **model:** correct reference silence trimming logic ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **model:** correct reference silence trimming logic ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **model:** correct reference silence trimming logic ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **model:** correct reference silence trimming logic ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **model:** correct reference silence trimming logic ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **model:** correct reference silence trimming logic ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **model:** correct reference silence trimming logic ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **model:** correct reference silence trimming logic ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **model:** correct reference silence trimming logic ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **model:** correct reference silence trimming logic ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **model:** correct reference silence trimming logic ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **model:** correct reference silence trimming logic ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **model:** correct reference silence trimming logic ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **model:** correct reference silence trimming logic ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **model:** correct reference silence trimming logic ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **model:** correct reference silence trimming logic ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **model:** correct reference silence trimming logic ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **model:** correct reference silence trimming logic ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **model:** correct reference silence trimming logic ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **model:** correct reference silence trimming logic ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **model:** correct reference silence trimming logic ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **model:** correct reference silence trimming logic ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **model:** correct reference silence trimming logic ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **model:** correct reference silence trimming logic ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **model:** correct reference silence trimming logic ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **model:** correct reference silence trimming logic ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **model:** correct reference silence trimming logic ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **model:** correct reference silence trimming logic ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **model:** correct reference silence trimming logic ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **model:** correct reference silence trimming logic ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **model:** correct reference silence trimming logic ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **model:** correct reference silence trimming logic ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **model:** correct reference silence trimming logic ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **model:** correct reference silence trimming logic ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **model:** correct reference silence trimming logic ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **model:** correct reference silence trimming logic ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **model:** correct reference silence trimming logic ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **model:** correct reference silence trimming logic ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **model:** correct reference silence trimming logic ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **model:** correct reference silence trimming logic ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **model:** correct reference silence trimming logic ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **model:** correct reference silence trimming logic ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **model:** correct reference silence trimming logic ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **model:** correct reference silence trimming logic ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **model:** correct reference silence trimming logic ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **model:** correct reference silence trimming logic ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **model:** correct reference silence trimming logic ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **model:** correct reference silence trimming logic ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **model:** correct reference silence trimming logic ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **model:** correct reference silence trimming logic ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **model:** correct reference silence trimming logic ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **model:** correct reference silence trimming logic ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **model:** correct reference silence trimming logic ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **model:** correct reference silence trimming logic ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **model:** correct reference silence trimming logic ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **model:** correct reference silence trimming logic ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **model:** correct reference silence trimming logic ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **model:** correct reference silence trimming logic ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **model:** correct reference silence trimming logic ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **model:** correct reference silence trimming logic ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **model:** correct reference silence trimming logic ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **model:** correct reference silence trimming logic ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **model:** correct reference silence trimming logic ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **model:** correct reference silence trimming logic ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **model:** correct reference silence trimming logic ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **model:** correct reference silence trimming logic ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **model:** correct reference silence trimming logic ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **model:** correct seed max from 2^63-1 to 2^32-1 ([6748b8b](https://github.com/nmorgowicz-org/persona-forge/commit/6748b8bf4b622d024d059101ee7e942feff45959))
* **openvino:** auto-size OV_INFERENCE_THREADS from host core count ([de12867](https://github.com/nmorgowicz-org/persona-forge/commit/de128675154a3240735cb45651f6af5e63fe89f1))
* **openvino:** auto-size OV_INFERENCE_THREADS from host core count ([c9b9cde](https://github.com/nmorgowicz-org/persona-forge/commit/c9b9cdec38aacddcf7774c1b185a1585204e4551))
* patch codec_head.forward instead of replacing codec_head module ([9cc9863](https://github.com/nmorgowicz-org/persona-forge/commit/9cc98630a9ce5dc52502ef9585cdfed30117ffcb))
* patch qwen-tts input_embeds -&gt; inputs_embeds for transformers 5.x ([8159e7d](https://github.com/nmorgowicz-org/persona-forge/commit/8159e7d85821793ef9ea475670a4b79cc1e33dd0))
* **prosody:** restore healthy voice-style baseline ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **prosody:** restore healthy voice-style baseline ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **prosody:** restore healthy voice-style baseline ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **prosody:** restore healthy voice-style baseline ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **prosody:** restore healthy voice-style baseline ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **prosody:** restore healthy voice-style baseline ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **prosody:** restore healthy voice-style baseline ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **prosody:** restore healthy voice-style baseline ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **prosody:** restore healthy voice-style baseline ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **prosody:** restore healthy voice-style baseline ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **prosody:** restore healthy voice-style baseline ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **prosody:** restore healthy voice-style baseline ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **prosody:** restore healthy voice-style baseline ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **prosody:** restore healthy voice-style baseline ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **prosody:** restore healthy voice-style baseline ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **prosody:** restore healthy voice-style baseline ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **prosody:** restore healthy voice-style baseline ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **prosody:** restore healthy voice-style baseline ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **prosody:** restore healthy voice-style baseline ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **prosody:** restore healthy voice-style baseline ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **prosody:** restore healthy voice-style baseline ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **prosody:** restore healthy voice-style baseline ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **prosody:** restore healthy voice-style baseline ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **prosody:** restore healthy voice-style baseline ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **prosody:** restore healthy voice-style baseline ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **prosody:** restore healthy voice-style baseline ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **prosody:** restore healthy voice-style baseline ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **prosody:** restore healthy voice-style baseline ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **prosody:** restore healthy voice-style baseline ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **prosody:** restore healthy voice-style baseline ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **prosody:** restore healthy voice-style baseline ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **prosody:** restore healthy voice-style baseline ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **prosody:** restore healthy voice-style baseline ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **prosody:** restore healthy voice-style baseline ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **prosody:** restore healthy voice-style baseline ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **prosody:** restore healthy voice-style baseline ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **prosody:** restore healthy voice-style baseline ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **prosody:** restore healthy voice-style baseline ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **prosody:** restore healthy voice-style baseline ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **prosody:** restore healthy voice-style baseline ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **prosody:** restore healthy voice-style baseline ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **prosody:** restore healthy voice-style baseline ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **prosody:** restore healthy voice-style baseline ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **prosody:** restore healthy voice-style baseline ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **prosody:** restore healthy voice-style baseline ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **prosody:** restore healthy voice-style baseline ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **prosody:** restore healthy voice-style baseline ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **prosody:** restore healthy voice-style baseline ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **prosody:** restore healthy voice-style baseline ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **prosody:** restore healthy voice-style baseline ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **prosody:** restore healthy voice-style baseline ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **prosody:** restore healthy voice-style baseline ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **prosody:** restore healthy voice-style baseline ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **prosody:** restore healthy voice-style baseline ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **prosody:** restore healthy voice-style baseline ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **prosody:** restore healthy voice-style baseline ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **prosody:** restore healthy voice-style baseline ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **prosody:** restore healthy voice-style baseline ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **prosody:** restore healthy voice-style baseline ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **prosody:** restore healthy voice-style baseline ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **prosody:** restore healthy voice-style baseline ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **prosody:** restore healthy voice-style baseline ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **prosody:** restore healthy voice-style baseline ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **prosody:** restore healthy voice-style baseline ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **prosody:** restore healthy voice-style baseline ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **prosody:** restore healthy voice-style baseline ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **prosody:** restore healthy voice-style baseline ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **prosody:** restore healthy voice-style baseline ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **prosody:** restore healthy voice-style baseline ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **prosody:** restore healthy voice-style baseline ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **prosody:** restore healthy voice-style baseline ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **prosody:** restore healthy voice-style baseline ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **prosody:** restore healthy voice-style baseline ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **prosody:** restore healthy voice-style baseline ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **prosody:** restore healthy voice-style baseline ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **prosody:** restore healthy voice-style baseline ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **prosody:** restore healthy voice-style baseline ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **prosody:** restore healthy voice-style baseline ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **prosody:** restore healthy voice-style baseline ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **prosody:** restore healthy voice-style baseline ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **prosody:** restore healthy voice-style baseline ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **prosody:** restore healthy voice-style baseline ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **prosody:** restore healthy voice-style baseline ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **prosody:** restore healthy voice-style baseline ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **prosody:** restore healthy voice-style baseline ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **prosody:** restore healthy voice-style baseline ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **prosody:** restore healthy voice-style baseline ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **prosody:** restore healthy voice-style baseline ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **prosody:** restore healthy voice-style baseline ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **prosody:** restore healthy voice-style baseline ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **prosody:** restore healthy voice-style baseline ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **prosody:** restore healthy voice-style baseline ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **prosody:** restore healthy voice-style baseline ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **prosody:** restore healthy voice-style baseline ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **prosody:** restore healthy voice-style baseline ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **prosody:** restore healthy voice-style baseline ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **prosody:** restore healthy voice-style baseline ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **prosody:** restore healthy voice-style baseline ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **prosody:** restore healthy voice-style baseline ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **prosody:** restore healthy voice-style baseline ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **prosody:** restore healthy voice-style baseline ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **prosody:** restore healthy voice-style baseline ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **prosody:** restore healthy voice-style baseline ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **prosody:** restore healthy voice-style baseline ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **prosody:** restore healthy voice-style baseline ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **prosody:** restore healthy voice-style baseline ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **prosody:** restore healthy voice-style baseline ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **prosody:** restore healthy voice-style baseline ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **prosody:** restore healthy voice-style baseline ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **prosody:** restore healthy voice-style baseline ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **prosody:** restore healthy voice-style baseline ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **prosody:** restore healthy voice-style baseline ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **prosody:** restore healthy voice-style baseline ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **prosody:** restore healthy voice-style baseline ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **prosody:** restore healthy voice-style baseline ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **prosody:** restore healthy voice-style baseline ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **prosody:** restore healthy voice-style baseline ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **prosody:** restore healthy voice-style baseline ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **prosody:** restore healthy voice-style baseline ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **prosody:** restore healthy voice-style baseline ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **prosody:** restore healthy voice-style baseline ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **prosody:** restore healthy voice-style baseline ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **prosody:** restore healthy voice-style baseline ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **pytorch:** patch T5-generation prepare_inputs_for_generation, create_causal_mask, and sdpa_attention_forward for transformers 5.x ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **release:** preserve every commit override entry ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **runtime,tests:** backend-aware generation caps + CI validate fixes ([#135](https://github.com/nmorgowicz-org/persona-forge/issues/135)) ([b411d84](https://github.com/nmorgowicz-org/persona-forge/commit/b411d845ca7803cc66e6c41b712c3f432a8156e1))
* **runtime:** correct _single_chunk left-context warmup and return types; add fallback warnings ([a78be3d](https://github.com/nmorgowicz-org/persona-forge/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **runtime:** correct vocoder IR 2D/3D shape unpack in _run_ir ([a78be3d](https://github.com/nmorgowicz-org/persona-forge/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **runtime:** correct vocoder multi-chunk waveform slicing and tensor copy ([a78be3d](https://github.com/nmorgowicz-org/persona-forge/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **runtime:** drop jemalloc from LOW_RAM_MODE; keep idle unload ([d5f3ad5](https://github.com/nmorgowicz-org/persona-forge/commit/d5f3ad5ff036d6bf6ef9e5898fea7930b8db5335))
* **runtime:** exclude internal 'vocoder' key from OpenVINO CPU compile_model config ([5d56038](https://github.com/nmorgowicz-org/persona-forge/commit/5d56038c8d35f219e3ced4672392e71628b784fa))
* **runtime:** fix transformers 5.x weight over-initialization randomizing talker embeddings and heads ([2092df3](https://github.com/nmorgowicz-org/persona-forge/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))
* **runtime:** force correct decode position_ids in OV cores ([5ea00db](https://github.com/nmorgowicz-org/persona-forge/commit/5ea00dbde2592d27a6d3682b9b776a1810855c0d))
* **runtime:** gate bf16→float32 auto-fallback and cache fallback voice_state ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** glibc malloc tuning for LOW_RAM_MODE; drop LD_PRELOAD ([85f2014](https://github.com/nmorgowicz-org/persona-forge/commit/85f201445d28c8faceae9f7595d532fa99c85736))
* **runtime:** gracefully handle missing faster_whisper instead of crashing at import ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** honor BF16 serving load settings in app_worker ([d67a505](https://github.com/nmorgowicz-org/persona-forge/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))
* **runtime:** include ov_vocoder_runtime.py in runtime image ([0e3d13c](https://github.com/nmorgowicz-org/persona-forge/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))
* **runtime:** resolve vocoder IR filename; add per-core precision + audio dump ([8739289](https://github.com/nmorgowicz-org/persona-forge/commit/87392896d8db155ea541ad8cc70251926c4e429b))
* **runtime:** restore Mimi causal mask for correct reference codec tokens under transformers 5.x ([2092df3](https://github.com/nmorgowicz-org/persona-forge/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))
* **runtime:** suppress transformers 5.x deprecation warnings ([aea333a](https://github.com/nmorgowicz-org/persona-forge/commit/aea333a7842c5af3884442a08050cdfce155d668))
* **runtime:** unbreak pytorch rollback, harden formats, doc memory root cause ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **runtime:** validate requests before busy state ([4ae3a9d](https://github.com/nmorgowicz-org/persona-forge/commit/4ae3a9df1ab429e8b44d3a3f745b1b869015fc5a))
* **runtime:** validate requests before busy state ([1c95831](https://github.com/nmorgowicz-org/persona-forge/commit/1c95831dad8fa1b66640d2871ca67cf518199a38))
* **runtime:** validate requests before busy state ([2a2842a](https://github.com/nmorgowicz-org/persona-forge/commit/2a2842a5f2206547e758dad36184cfac7e0fc89e))
* **runtime:** validate requests before busy state ([4418a23](https://github.com/nmorgowicz-org/persona-forge/commit/4418a23bbef9716223b3a5a01535185f5967b1a4))
* **runtime:** validate requests before busy state ([ca4e2e8](https://github.com/nmorgowicz-org/persona-forge/commit/ca4e2e8de2fb996b64e94a131f09cf82344dacb7))
* **runtime:** validate requests before busy state ([2effdc7](https://github.com/nmorgowicz-org/persona-forge/commit/2effdc7feae0721b65cb021f9fc8efa7391c1644))
* **runtime:** validate requests before busy state ([ff53537](https://github.com/nmorgowicz-org/persona-forge/commit/ff53537e8d74fc11fad3f8f4584e676044b438bd))
* **runtime:** validate requests before busy state ([d553f8a](https://github.com/nmorgowicz-org/persona-forge/commit/d553f8a9d10e294968a1d288821e201a6712f576))
* **runtime:** validate requests before busy state ([2a967da](https://github.com/nmorgowicz-org/persona-forge/commit/2a967da0d22fc6b9ebbaf2e983b61b5c5231d1e5))
* **runtime:** validate requests before busy state ([8588b78](https://github.com/nmorgowicz-org/persona-forge/commit/8588b78094c755cfd82a53d04b929a1e3ef324eb))
* **runtime:** validate requests before busy state ([9804f4e](https://github.com/nmorgowicz-org/persona-forge/commit/9804f4e65e94857eb22d30b56e19e0472b070220))
* **runtime:** validate requests before busy state ([34cf6c8](https://github.com/nmorgowicz-org/persona-forge/commit/34cf6c80c42ad86354d170a2c9c0ee99bfbd5b52))
* **runtime:** validate requests before busy state ([080ef17](https://github.com/nmorgowicz-org/persona-forge/commit/080ef17e9c4e50ff48ab1e34bb82df4932a1faf6))
* **runtime:** validate requests before busy state ([e266704](https://github.com/nmorgowicz-org/persona-forge/commit/e266704b8006f948e2e28767230396b16d4c81d9))
* **runtime:** validate requests before busy state ([c66d853](https://github.com/nmorgowicz-org/persona-forge/commit/c66d8539b26a4294da982995af95f14b3eda201b))
* **runtime:** validate requests before busy state ([dd28346](https://github.com/nmorgowicz-org/persona-forge/commit/dd283460f36025185177e95ee16b7f0a909193aa))
* **runtime:** validate requests before busy state ([150e4ce](https://github.com/nmorgowicz-org/persona-forge/commit/150e4ce2f13c3427f188822fc5853f6a4e675b6f))
* **runtime:** validate requests before busy state ([b0f6bd8](https://github.com/nmorgowicz-org/persona-forge/commit/b0f6bd8e05d3dc2ae44d248cd38aeb1b022fc5d5))
* **runtime:** validate requests before busy state ([a73a1d3](https://github.com/nmorgowicz-org/persona-forge/commit/a73a1d338451527d7770306d62491ff01029ac50))
* **runtime:** validate requests before busy state ([c667d86](https://github.com/nmorgowicz-org/persona-forge/commit/c667d867a09e39a3875939eeae22a222e1920e87))
* **runtime:** validate requests before busy state ([8ac67d7](https://github.com/nmorgowicz-org/persona-forge/commit/8ac67d7ecc88ebea70ea1c6397d06be5f45ca92a))
* **runtime:** validate requests before busy state ([6e6c094](https://github.com/nmorgowicz-org/persona-forge/commit/6e6c0940af737662a79b796c6f40a783919f3730))
* **runtime:** validate requests before busy state ([52d4e9b](https://github.com/nmorgowicz-org/persona-forge/commit/52d4e9bd603e264a50e430d986c5400ef0bbe153))
* **runtime:** validate requests before busy state ([3b1b097](https://github.com/nmorgowicz-org/persona-forge/commit/3b1b097bf04c2d612b8e464fd018f773f48d11ec))
* **runtime:** validate requests before busy state ([abd54bb](https://github.com/nmorgowicz-org/persona-forge/commit/abd54bb1865de97e9a5b39fb0f9faae3db5d6cb4))
* **runtime:** validate requests before busy state ([e77767c](https://github.com/nmorgowicz-org/persona-forge/commit/e77767c5306516793889d54cd1c66818c85a8ff9))
* **runtime:** validate requests before busy state ([f50e29c](https://github.com/nmorgowicz-org/persona-forge/commit/f50e29cfc95d09b66360c6103a03852d5e1e7012))
* **runtime:** validate requests before busy state ([7770b79](https://github.com/nmorgowicz-org/persona-forge/commit/7770b79780f8fefed488242e60ba482b24697459))
* **runtime:** validate requests before busy state ([c5f75c8](https://github.com/nmorgowicz-org/persona-forge/commit/c5f75c8c688ecc8b35e26b0d1a2636f83cf5470f))
* **runtime:** validate requests before busy state ([f11a0af](https://github.com/nmorgowicz-org/persona-forge/commit/f11a0af473b16a4fb9b385598672247da9a3cc00))
* **runtime:** validate requests before busy state ([acfe4ef](https://github.com/nmorgowicz-org/persona-forge/commit/acfe4ef6b09d609b8164d5cd674f8aef98bb70d7))
* **runtime:** validate requests before busy state ([de35c7c](https://github.com/nmorgowicz-org/persona-forge/commit/de35c7ce0c012cd5afa6a2a25fbca34df7a6d514))
* **runtime:** validate requests before busy state ([eecc211](https://github.com/nmorgowicz-org/persona-forge/commit/eecc211f6f73cf7e84e91c40bb871276fe624b88))
* **runtime:** validate requests before busy state ([88d0149](https://github.com/nmorgowicz-org/persona-forge/commit/88d0149ba0e0259843a61bb9d666c455163ea249))
* **runtime:** validate requests before busy state ([ad23806](https://github.com/nmorgowicz-org/persona-forge/commit/ad238060e869570231f2baa4b037614d4747ff6c))
* **runtime:** validate requests before busy state ([857a9e8](https://github.com/nmorgowicz-org/persona-forge/commit/857a9e83637935ec6723de9cab85785cfc9fed88))
* **runtime:** validate requests before busy state ([25b55b3](https://github.com/nmorgowicz-org/persona-forge/commit/25b55b35e2a107db999c88fe431843e02358e932))
* **runtime:** validate requests before busy state ([721bb1b](https://github.com/nmorgowicz-org/persona-forge/commit/721bb1bdf5b764c1c5f5d35a3f3b3a4d6eb77efe))
* **runtime:** validate requests before busy state ([8b8f18b](https://github.com/nmorgowicz-org/persona-forge/commit/8b8f18b8f64643f82926ba839672ca31423f62dd))
* **runtime:** validate requests before busy state ([5408049](https://github.com/nmorgowicz-org/persona-forge/commit/540804979a947e23af6a2ba844165fb7acf664da))
* **runtime:** validate requests before busy state ([927ca9c](https://github.com/nmorgowicz-org/persona-forge/commit/927ca9ca833d47c83710e2efbc92a4c96ee33ddc))
* **runtime:** validate requests before busy state ([4f78f68](https://github.com/nmorgowicz-org/persona-forge/commit/4f78f6868d0dada1b60ec8ad6591549bb61bb8e5))
* **runtime:** validate requests before busy state ([0431351](https://github.com/nmorgowicz-org/persona-forge/commit/0431351a7d5e7ee4aec40d8887bac65914e507d3))
* **runtime:** validate requests before busy state ([76275f0](https://github.com/nmorgowicz-org/persona-forge/commit/76275f0d12b07ef0461997d4062465af50404697))
* **runtime:** validate requests before busy state ([91d0847](https://github.com/nmorgowicz-org/persona-forge/commit/91d084795dd8298598c8079e8d2d2561f93e35ec))
* **runtime:** validate requests before busy state ([e4a5b31](https://github.com/nmorgowicz-org/persona-forge/commit/e4a5b31fc808c550c3ab0be8eb7aec1e056dcc12))
* **runtime:** validate requests before busy state ([846cfda](https://github.com/nmorgowicz-org/persona-forge/commit/846cfda919f20208203e61212e30880d88600efa))
* **runtime:** validate requests before busy state ([c235a63](https://github.com/nmorgowicz-org/persona-forge/commit/c235a636d8add52e7999bc4e9e8faaacb378dd99))
* **runtime:** validate requests before busy state ([cdcb84c](https://github.com/nmorgowicz-org/persona-forge/commit/cdcb84c2df9d8aac705ad2241534a1fe3b462891))
* **runtime:** validate requests before busy state ([039b4ab](https://github.com/nmorgowicz-org/persona-forge/commit/039b4abc61514638410a75ea6e8c80667c65c991))
* **runtime:** validate requests before busy state ([4fbfb06](https://github.com/nmorgowicz-org/persona-forge/commit/4fbfb06d9ba7cd9ed0183de7c4aedca9d586c768))
* **runtime:** validate requests before busy state ([39505d0](https://github.com/nmorgowicz-org/persona-forge/commit/39505d09a49f62f6fc50a9c8505d6afa4b4580c2))
* **runtime:** validate requests before busy state ([ba549f5](https://github.com/nmorgowicz-org/persona-forge/commit/ba549f54256ebd88650bfa345ff7efcfdb7aa932))
* **runtime:** validate requests before busy state ([a5f4a11](https://github.com/nmorgowicz-org/persona-forge/commit/a5f4a112fd094fd30df073ed3ed45b765407ebe0))
* **runtime:** validate requests before busy state ([4aca7f6](https://github.com/nmorgowicz-org/persona-forge/commit/4aca7f66eef1bb8e8e57415184cca945c7e39988))
* **runtime:** validate requests before busy state ([d39a256](https://github.com/nmorgowicz-org/persona-forge/commit/d39a25688e03f4d9043438b795e92c396c4e3470))
* **runtime:** validate requests before busy state ([eec1bdf](https://github.com/nmorgowicz-org/persona-forge/commit/eec1bdf63a7a17b311c073a5295df85db9217272))
* **runtime:** validate requests before busy state ([e1d2ce1](https://github.com/nmorgowicz-org/persona-forge/commit/e1d2ce1d08a7b6466cad686bb10695af5e1f9285))
* **runtime:** validate requests before busy state ([a9e1310](https://github.com/nmorgowicz-org/persona-forge/commit/a9e1310c079a2dad4b5193c9515f529bd66ac8f5))
* **runtime:** validate requests before busy state ([9941c37](https://github.com/nmorgowicz-org/persona-forge/commit/9941c37e19af87aecc46af5814d66459bad61e34))
* **runtime:** validate requests before busy state ([c65c1b8](https://github.com/nmorgowicz-org/persona-forge/commit/c65c1b8d356a1c05c59a15d8b7bbf3ad2f99db12))
* **runtime:** validate requests before busy state ([09bda91](https://github.com/nmorgowicz-org/persona-forge/commit/09bda91ac5774e1cb48a2533d20c718fb8ade115))
* **runtime:** validate requests before busy state ([a7a52f9](https://github.com/nmorgowicz-org/persona-forge/commit/a7a52f9bef52e87678e7e70f96d7ba047184eaf2))
* **runtime:** validate requests before busy state ([5219715](https://github.com/nmorgowicz-org/persona-forge/commit/5219715d0376e8c9287d776c02d73054f57ca779))
* **runtime:** validate requests before busy state ([16ca135](https://github.com/nmorgowicz-org/persona-forge/commit/16ca1350c51bfb5a13b5eff02ffb73752b85665c))
* **runtime:** validate requests before busy state ([e78889d](https://github.com/nmorgowicz-org/persona-forge/commit/e78889d9b6bb80e2554f53e20c2e3d8dea6d33b1))
* **runtime:** validate requests before busy state ([009cf60](https://github.com/nmorgowicz-org/persona-forge/commit/009cf604cb60c61a5ef4efaf165a739f4bd5bffe))
* **runtime:** validate requests before busy state ([5075c63](https://github.com/nmorgowicz-org/persona-forge/commit/5075c630723bee91d8250b55887c41e50ef0a0ab))
* **runtime:** validate requests before busy state ([a496dbd](https://github.com/nmorgowicz-org/persona-forge/commit/a496dbd94a38cfe2c4d0a6ec53559a1bb91062f8))
* **runtime:** validate requests before busy state ([e9dde3a](https://github.com/nmorgowicz-org/persona-forge/commit/e9dde3a531ce31e4602295d4a17ad85c12f19bcd))
* **runtime:** validate requests before busy state ([86de8ec](https://github.com/nmorgowicz-org/persona-forge/commit/86de8ecd58076ddb6da716b0372fc11c222cfd2c))
* **runtime:** validate requests before busy state ([4ba522e](https://github.com/nmorgowicz-org/persona-forge/commit/4ba522ec58fbf38db65567bbdc66d50b78e6f10f))
* **runtime:** validate requests before busy state ([7ff066c](https://github.com/nmorgowicz-org/persona-forge/commit/7ff066cbf65b54cfcfa5169eeeab0573eaafac84))
* **runtime:** validate requests before busy state ([6301f8c](https://github.com/nmorgowicz-org/persona-forge/commit/6301f8c9f5c0eba03a237d150e4d7623d2048bfa))
* **runtime:** validate requests before busy state ([dcfbfb0](https://github.com/nmorgowicz-org/persona-forge/commit/dcfbfb0dc8f6d694c1f05246d4d02c2efa8feee9))
* **runtime:** validate requests before busy state ([abd0faf](https://github.com/nmorgowicz-org/persona-forge/commit/abd0fafcce73cc103d7a099075e3155adc2c8f1e))
* **runtime:** validate requests before busy state ([387372f](https://github.com/nmorgowicz-org/persona-forge/commit/387372f5eccc7f0d8ac3b3d8ec2a0b203f3865c1))
* **runtime:** validate requests before busy state ([ddd8e20](https://github.com/nmorgowicz-org/persona-forge/commit/ddd8e2029317ebc4302075180113f7210929c97d))
* **runtime:** validate requests before busy state ([54cae32](https://github.com/nmorgowicz-org/persona-forge/commit/54cae32e16a376762f8851565d4613096aa69170))
* **runtime:** validate requests before busy state ([0d855a1](https://github.com/nmorgowicz-org/persona-forge/commit/0d855a17ca04d6b0476108c9bc64dc5862c01e03))
* **runtime:** validate requests before busy state ([57b6f5b](https://github.com/nmorgowicz-org/persona-forge/commit/57b6f5b676c8eafb6328156dcc326a39a31ecf9c))
* **runtime:** validate requests before busy state ([692d063](https://github.com/nmorgowicz-org/persona-forge/commit/692d06360e969ea4d5209629607ecc99058cf29f))
* **runtime:** validate requests before busy state ([c4e7c68](https://github.com/nmorgowicz-org/persona-forge/commit/c4e7c68c8923cb899bcc82cdeaf2617e0da3081c))
* **runtime:** validate requests before busy state ([1febadb](https://github.com/nmorgowicz-org/persona-forge/commit/1febadb659697376707f1d56aa8d0f5df42a51b7))
* **runtime:** validate requests before busy state ([92030d6](https://github.com/nmorgowicz-org/persona-forge/commit/92030d64af9a46167a7a5838ab5114000130d1e0))
* **runtime:** validate requests before busy state ([b7c0ffa](https://github.com/nmorgowicz-org/persona-forge/commit/b7c0ffa652f0c505de88818c6bcbe7a91fcbd905))
* **runtime:** validate requests before busy state ([dc47d9e](https://github.com/nmorgowicz-org/persona-forge/commit/dc47d9e68f2ba1cdd70c46aadd0f3f26319b6ff6))
* **runtime:** validate requests before busy state ([b262bed](https://github.com/nmorgowicz-org/persona-forge/commit/b262bed553bfcb4ab477b00497e510a1ccae9779))
* **runtime:** validate requests before busy state ([8ce337d](https://github.com/nmorgowicz-org/persona-forge/commit/8ce337d9b2fbdb7d593887303448ff5ecabe0318))
* **runtime:** validate requests before busy state ([e8c4a4c](https://github.com/nmorgowicz-org/persona-forge/commit/e8c4a4ca78d792471b5ad4c16cc3380aa2874bd4))
* **runtime:** validate requests before busy state ([f124d70](https://github.com/nmorgowicz-org/persona-forge/commit/f124d704f6352c2cdac490c855dc870624e85cb3))
* **runtime:** validate requests before busy state ([9d1fa79](https://github.com/nmorgowicz-org/persona-forge/commit/9d1fa79aeb798436c0b8d0cb331d594438269f56))
* **runtime:** validate requests before busy state ([3727cfb](https://github.com/nmorgowicz-org/persona-forge/commit/3727cfbf2745d7b8259e134c63765fbedc4b033b))
* **runtime:** validate requests before busy state ([8ebeb80](https://github.com/nmorgowicz-org/persona-forge/commit/8ebeb801ad5bb72460ca24245b06e01e02052a80))
* **runtime:** validate requests before busy state ([de9d3e4](https://github.com/nmorgowicz-org/persona-forge/commit/de9d3e43aa655a4843cf91ad679f3659764b3b34))
* **runtime:** validate requests before busy state ([5a2c72b](https://github.com/nmorgowicz-org/persona-forge/commit/5a2c72ba3aff896c995c4341d45d42a7e06f3595))
* **runtime:** validate requests before busy state ([5b513b7](https://github.com/nmorgowicz-org/persona-forge/commit/5b513b716017ef7ecd4137037a8c36960074c389))
* **runtime:** validate requests before busy state ([f983eb3](https://github.com/nmorgowicz-org/persona-forge/commit/f983eb3b34880085f30d6bf2a2f8423c1de083a1))
* **runtime:** validate requests before busy state ([f813770](https://github.com/nmorgowicz-org/persona-forge/commit/f81377010434dbda828f2f45f8a4fffdfa199be1))
* **runtime:** validate requests before busy state ([9c1bdc8](https://github.com/nmorgowicz-org/persona-forge/commit/9c1bdc8f86de30a54cbad8345417b22a0201e25a))
* **runtime:** validate requests before busy state ([aff7bc9](https://github.com/nmorgowicz-org/persona-forge/commit/aff7bc9d8e0596ceb2e80de57129dc88f8631c4a))
* **runtime:** validate requests before busy state ([62ee896](https://github.com/nmorgowicz-org/persona-forge/commit/62ee896ae0d0f55735d1bc8eecfed682af4fcca3))
* **runtime:** validate requests before busy state ([2eec1e2](https://github.com/nmorgowicz-org/persona-forge/commit/2eec1e2afef9c608f4a89b0e78e3e4636a5fdd57))
* **runtime:** validate requests before busy state ([43c5fbf](https://github.com/nmorgowicz-org/persona-forge/commit/43c5fbf36d70cc16a711191c3372ca7bd6b022f4))
* **runtime:** validate requests before busy state ([e8c19d1](https://github.com/nmorgowicz-org/persona-forge/commit/e8c19d1674dd5980b543a8435e9d54c53cd68b69))
* **runtime:** validate requests before busy state ([7485a7d](https://github.com/nmorgowicz-org/persona-forge/commit/7485a7d6eaf1a5b7457e83d476300fbe0eefe1c2))
* **runtime:** validate requests before busy state ([1f58e1f](https://github.com/nmorgowicz-org/persona-forge/commit/1f58e1f784de51d8fdeed968b5bbd707ef676165))
* **runtime:** validate requests before busy state ([68ed002](https://github.com/nmorgowicz-org/persona-forge/commit/68ed0020039b4ba028db01a13f3b71b2988d6e6c))
* **runtime:** validate requests before busy state ([76a82d7](https://github.com/nmorgowicz-org/persona-forge/commit/76a82d7faac6b99a56f651384f99af8e10d4f15c))
* **runtime:** validate requests before busy state ([ef3fb87](https://github.com/nmorgowicz-org/persona-forge/commit/ef3fb872c1ea63d7259027c33b08b7969d75f1ac))
* **runtime:** validate requests before busy state ([97b39f6](https://github.com/nmorgowicz-org/persona-forge/commit/97b39f6acfcac905c1cf7e18965587ec1480769e))
* **runtime:** validate requests before busy state ([a06a630](https://github.com/nmorgowicz-org/persona-forge/commit/a06a6302d13c712d0f08bf7cb3ec09d184a62cfd))
* **runtime:** validate requests before busy state ([05c7aa5](https://github.com/nmorgowicz-org/persona-forge/commit/05c7aa50abf181a188bbb0b4f4a1372dd323be82))
* **runtime:** validate requests before busy state ([c792dee](https://github.com/nmorgowicz-org/persona-forge/commit/c792deebc7d314636a2c8dd2b5bb4093bf04fb23))
* **runtime:** validate requests before busy state ([f872f2a](https://github.com/nmorgowicz-org/persona-forge/commit/f872f2a9e47908c9ef4ae996a8657b19a2b1d47b))
* **runtime:** validate requests before busy state ([5a24130](https://github.com/nmorgowicz-org/persona-forge/commit/5a241303a7a57ef9808a6feb6b3212a909accdaf))
* **runtime:** validate requests before busy state ([afc89c5](https://github.com/nmorgowicz-org/persona-forge/commit/afc89c548113b261ab1564673247afe9339fcfb1))
* **runtime:** validate requests before busy state ([ab79148](https://github.com/nmorgowicz-org/persona-forge/commit/ab7914812ff74f5256fe23e6476c4f8b0c4f215d))
* **runtime:** validate requests before busy state ([9a2fb62](https://github.com/nmorgowicz-org/persona-forge/commit/9a2fb62292e5db0aaa2178e9caed25051a1062f5))
* **runtime:** validate requests before busy state ([c213c1b](https://github.com/nmorgowicz-org/persona-forge/commit/c213c1b18198bfe8eaf67452286490253df330bd))
* **runtime:** validate requests before busy state ([6fc3fcc](https://github.com/nmorgowicz-org/persona-forge/commit/6fc3fcc5e395874503847aed834c715ea4ca2f8d))
* **runtime:** validate requests before busy state ([f60b444](https://github.com/nmorgowicz-org/persona-forge/commit/f60b4447d9ff6673dd8ea756fe5d2ab475747774))
* **runtime:** validate requests before busy state ([beb0851](https://github.com/nmorgowicz-org/persona-forge/commit/beb08513a7e6589b2aa23a6d77c14181a0e16a05))
* **scripts:** default M4 reference WAV to persistent project-owned path on docker-agent ([5717ddb](https://github.com/nmorgowicz-org/persona-forge/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))
* **serve:** drop gunicorn --preload from single-worker model server ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **test:** harden code normalization, seed greedy runs, gc for mode=all, add entropy metric ([a78be3d](https://github.com/nmorgowicz-org/persona-forge/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **tests:** repair CI test failures from stale fakes and pytest-only test module ([1d56671](https://github.com/nmorgowicz-org/persona-forge/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **tests:** silence werkzeug per-request access log in the E2E fake server ([1d56671](https://github.com/nmorgowicz-org/persona-forge/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **vocoder:** actually wire the OpenVINO vocoder + add backend provenance ([8739289](https://github.com/nmorgowicz-org/persona-forge/commit/87392896d8db155ea541ad8cc70251926c4e429b))


### Performance Improvements

* **m9:** release PyTorch weights before main-graph compile ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Code Refactoring

* **config:** add MODEL_SIZE presets + apply_preset_env (validated) ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **frontend:** centralize health, swap, runtime config, and speak-page state in Zustand store; refactor SpeakPage and useSwapStatus ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **service:** simplify runtime and local export ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **wip:** scaffold src/qwen3_tts package + write simplify-v2 HANDOFF ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))


### Tests

* add test_pocket_tts_runtime and test_run_generate for watchdog/watchdog-regression and Pocket TTS behaviors ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **export:** add vocoder FP32/INT8 parity gate with SNR metrics ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** add warm vocoder benchmark harness ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** update tests for relaxed provenance and current behavior ([e9d9943](https://github.com/nmorgowicz-org/persona-forge/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **m4:** add sampled-quality and logits-parity modes to parity harness ([a78be3d](https://github.com/nmorgowicz-org/persona-forge/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **parity:** set fp32 gate to SNR &gt;= 60 dB (observed 72–91 dB on docker-agent) ([4c4c567](https://github.com/nmorgowicz-org/persona-forge/commit/4c4c567f915d51dc4400ae02f7ca772b4b70334f))
* **runtime:** cover stateful predictor generation-step defaults ([7a7b091](https://github.com/nmorgowicz-org/persona-forge/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **runtime:** validate streaming code capture and transport parity ([d67a505](https://github.com/nmorgowicz-org/persona-forge/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))
* update voice design preset capacity to 360 ([6748b8b](https://github.com/nmorgowicz-org/persona-forge/commit/6748b8bf4b622d024d059101ee7e942feff45959))


### Documentation

* add conventional commit scopes to AGENTS.md ([6748b8b](https://github.com/nmorgowicz-org/persona-forge/commit/6748b8bf4b622d024d059101ee7e942feff45959))
* **agent-reference:** document delete/seed/runtime-config APIs, reorganize agent reference docs ([1d56671](https://github.com/nmorgowicz-org/persona-forge/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **compose:** explain :local tag vs production QWEN3_TTS_IMAGE usage ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **config:** group and expand .env.example with all user-facing vars ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* correct Release Please commit override syntax ([de12867](https://github.com/nmorgowicz-org/persona-forge/commit/de128675154a3240735cb45651f6af5e63fe89f1))
* document idle unload, OV cache, and LOW_RAM_MODE ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **handoff:** add a self-contained next-agent brief ([679799d](https://github.com/nmorgowicz-org/persona-forge/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **handoff:** record Task 4/5 progress and OpenAI endpoint ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **m4:** record measured FP32/INT8 generation results and next steps ([d7136c4](https://github.com/nmorgowicz-org/persona-forge/commit/d7136c4c4ef99f5cbe762ecad6879db0ede9ccc5))
* **m5:** record 1.7B INT4 results and the stateful-cache design ([679799d](https://github.com/nmorgowicz-org/persona-forge/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **m7:** document OPENVINO_RELEASE_TORCH approach and OpenVINO-only validation ([679799d](https://github.com/nmorgowicz-org/persona-forge/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **m9:** correct lifetime-peak root cause and refocus next steps on measuring it ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** listening check passed; update M9 gates status ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** record bf16 serving result (lifetime peak 11.6 to 8.3 GiB)$'\n\n'docs(m9): record bf16 quality-equivalent verdict; bf16 serving adopted$'\n\n'feat(serving): capacity-768 stateful main, silence trim, capacity-tuning docs ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** record M9 gate results (capacity, latency, concurrency, rollback) ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* mark M9 closed and shipped in v0.11.0; refresh handoff next steps ([d2dc334](https://github.com/nmorgowicz-org/persona-forge/commit/d2dc334fa974d109e2a588816d799aff7d481cf4))
* **plan:** add M4 FP32 re-validation (v0.8.0) benchmark results ([8739289](https://github.com/nmorgowicz-org/persona-forge/commit/87392896d8db155ea541ad8cc70251926c4e429b))
* **plan:** add M4 INT8 re-validation (v0.8.0) benchmark results ([8739289](https://github.com/nmorgowicz-org/persona-forge/commit/87392896d8db155ea541ad8cc70251926c4e429b))
* **plan:** note NNCF INT8 mode constraints (per-channel, all weights) ([ea762c3](https://github.com/nmorgowicz-org/persona-forge/commit/ea762c3b7c9920cf245b3ac205bb4243c4ddfd35))
* **plan:** record authoritative M3 INT8_ASYM characterization ([3570ad2](https://github.com/nmorgowicz-org/persona-forge/commit/3570ad2178f491fdba4c143088d680e08cf732ed))
* **plan:** record corrected M3 characterization and FP32-first runtime sequencing ([b320f0d](https://github.com/nmorgowicz-org/persona-forge/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))
* **plan:** record M1.5 validated results and update implementation status ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **plan:** record M3/M4 rationale and remaining gates ([e9d9943](https://github.com/nmorgowicz-org/persona-forge/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **plan:** record M4 verification run results and interpretation notes ([0e3d13c](https://github.com/nmorgowicz-org/persona-forge/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))
* **plan:** retire M4_NEXT_STEPS and update OPENVINO_IMPLEMENTATION with M4 next steps ([a78be3d](https://github.com/nmorgowicz-org/persona-forge/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **plans:** hermes TTS integration analysis and OpenAI-endpoint plan ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **plans:** record server-side voice decision and ref_audio reality ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* record codec-release A/B, reject INT8 vocoder, slim HANDOFF ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* record streaming listening verdict (identical, no seam) ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* refresh README + HOW_TO_RUN with 1.7B recommendation, footprint, codec flag ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* reorganize docs/plans into docs/dev with completed-feature rewrites; update all internal cross-references ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* restore advanced env var detail in .env.example and HOW_TO_RUN.md ([6748b8b](https://github.com/nmorgowicz-org/persona-forge/commit/6748b8bf4b622d024d059101ee7e942feff45959))
* **results:** correct memory root cause with measured data; rollback confirmed ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record 0.6B stateful footprint and quality gates ([7a7b091](https://github.com/nmorgowicz-org/persona-forge/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **results:** record completed transport and rollback tests ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **results:** record generation-peak A/B (0.6B vs 1.7B nearly identical) ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record listening preference ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record simplify-v2 validation ([d56456c](https://github.com/nmorgowicz-org/persona-forge/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record Task 3 per-core overlap go/no-go and preload fix ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **results:** record v0.13.0 baked-image streaming validation ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **run:** document no-preload memory fix and revised 1.7B footprint ([c5d082e](https://github.com/nmorgowicz-org/persona-forge/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **runtime:** record streaming results and operator runbook ([d67a505](https://github.com/nmorgowicz-org/persona-forge/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))
* simplify ENV_REFERENCE and .env.example for new users; add pocket_tts_integration architecture doc ([30ac7be](https://github.com/nmorgowicz-org/persona-forge/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* simplify README/HOW_TO_RUN; add RAM-tiered setup guidance ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* split benchmark results into OPENVINO_RESULTS.md ([1b11b1f](https://github.com/nmorgowicz-org/persona-forge/commit/1b11b1f7ddd65eff456061da8835477391d45af5))
* update AGENTS.md for single-image v0.15.1 ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))


### Continuous Integration

* **images:** protect active GHCR package versions during release cleanup ([538f29b](https://github.com/nmorgowicz-org/persona-forge/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))


### Miscellaneous Chores

* add codec_head logits diagnostic for decode-step debugging ([6df7709](https://github.com/nmorgowicz-org/persona-forge/commit/6df7709c12e00e27ccb2e639fcd4cfbcd0be9c08))
* **ci:** remove release-type from workflow ([c0c22af](https://github.com/nmorgowicz-org/persona-forge/commit/c0c22af22310c4abf9b316a816aadccc42841f5c))
* **deps:** disable renovate for transformers until qwen-tts bumps ([5340067](https://github.com/nmorgowicz-org/persona-forge/commit/5340067f52f012a87a8498499c593c7ab634526f))
* **deps:** install OmniVoice from git (398b6113), faster-whisper, pydub; add ffmpeg; add segment library volume ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **deps:** pin dependencies ([#97](https://github.com/nmorgowicz-org/persona-forge/issues/97)) ([035afc7](https://github.com/nmorgowicz-org/persona-forge/commit/035afc7353f8a1604fad48a18cd36ac70d6869c8))
* **deps:** pin python docker tag to 2b7445f ([#5](https://github.com/nmorgowicz-org/persona-forge/issues/5)) ([70adf0e](https://github.com/nmorgowicz-org/persona-forge/commit/70adf0ea127634f3827acb9d43525472377aa04d))
* **deps:** update dependency @fontsource-variable/geist to v5.3.0 ([#129](https://github.com/nmorgowicz-org/persona-forge/issues/129)) ([c3552fc](https://github.com/nmorgowicz-org/persona-forge/commit/c3552fcacf2c1d10e0a50a6bfdae6393a3f313cb))
* **deps:** update dependency lucide-react to v1.30.0 ([#124](https://github.com/nmorgowicz-org/persona-forge/issues/124)) ([a902062](https://github.com/nmorgowicz-org/persona-forge/commit/a902062afcbab4613b846c87f5422d42cb2b358c))
* **deps:** update dependency oxlint to ^1.72.0 ([#120](https://github.com/nmorgowicz-org/persona-forge/issues/120)) ([4988e19](https://github.com/nmorgowicz-org/persona-forge/commit/4988e19878fd9e553efa4a993d2c1924f07ff568))
* **deps:** update dependency pytest to v8.4.2 ([#106](https://github.com/nmorgowicz-org/persona-forge/issues/106)) ([f09009e](https://github.com/nmorgowicz-org/persona-forge/commit/f09009e2414b2b20ee907c63957595fcb6a6b01a))
* **deps:** update dependency pytest to v9 ([#107](https://github.com/nmorgowicz-org/persona-forge/issues/107)) ([cc9c593](https://github.com/nmorgowicz-org/persona-forge/commit/cc9c593d8c978429a2a16bd265bba2e8b21f03f8))
* **deps:** update dependency radix-ui to v1.6.7 ([#119](https://github.com/nmorgowicz-org/persona-forge/issues/119)) ([374dc0a](https://github.com/nmorgowicz-org/persona-forge/commit/374dc0a2bee1eab5fcd6a3ca4b690a812795741c))
* **deps:** update dependency shadcn to v4.13.0 ([#103](https://github.com/nmorgowicz-org/persona-forge/issues/103)) ([b9126c8](https://github.com/nmorgowicz-org/persona-forge/commit/b9126c854bb9ceeb4bdd7fd271dbd4bcac98fc43))
* **deps:** update dependency shadcn to v4.16.2 ([#128](https://github.com/nmorgowicz-org/persona-forge/issues/128)) ([c341874](https://github.com/nmorgowicz-org/persona-forge/commit/c341874c2914f6c5da60ab4f0806d47b1a70becb))
* **deps:** update dependency torch to v2.13.0 ([#118](https://github.com/nmorgowicz-org/persona-forge/issues/118)) ([cd3d731](https://github.com/nmorgowicz-org/persona-forge/commit/cd3d731bf30d1a5069de489e208192f1575f8198))
* **deps:** update dependency vite to ^8.2.1 ([#123](https://github.com/nmorgowicz-org/persona-forge/issues/123)) ([5a59f1d](https://github.com/nmorgowicz-org/persona-forge/commit/5a59f1db42d01f3149a050b5f841dee2382c051b))
* **deps:** update node.js to 3638d9a ([#126](https://github.com/nmorgowicz-org/persona-forge/issues/126)) ([4964e63](https://github.com/nmorgowicz-org/persona-forge/commit/4964e6370517e8525f54228669f2bf2649fbea03))
* **deps:** update node.js to cb4e8f7 ([#115](https://github.com/nmorgowicz-org/persona-forge/issues/115)) ([06fd976](https://github.com/nmorgowicz-org/persona-forge/commit/06fd976002d7707a4716fb060d83981455cbed7c))
* **deps:** update openvino stack ([#132](https://github.com/nmorgowicz-org/persona-forge/issues/132)) ([cad3469](https://github.com/nmorgowicz-org/persona-forge/commit/cad346936c7351502df2b01f05fe89280a6cbf86))
* **deps:** update python:3.13-slim docker digest to eb43ff1 ([#54](https://github.com/nmorgowicz-org/persona-forge/issues/54)) ([f584a0c](https://github.com/nmorgowicz-org/persona-forge/commit/f584a0c0ecc34a1ea2e7e45aaf9fb78c18100bc1))
* **deps:** update python:3.13-slim docker digest to ffb752e ([#127](https://github.com/nmorgowicz-org/persona-forge/issues/127)) ([e917076](https://github.com/nmorgowicz-org/persona-forge/commit/e917076009864276a9707b03b03434769566d7ec))
* **deps:** update react monorepo ([#130](https://github.com/nmorgowicz-org/persona-forge/issues/130)) ([bd75ef6](https://github.com/nmorgowicz-org/persona-forge/commit/bd75ef6a113c7cdb0bc3060e59e22a0d9bdbb196))
* ignore .DS_Store ([8739289](https://github.com/nmorgowicz-org/persona-forge/commit/87392896d8db155ea541ad8cc70251926c4e429b))
* **m9:** drop committed raw RSS profile and reject raw profiles in repo guard ([08415a5](https://github.com/nmorgowicz-org/persona-forge/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* Milestone 0 baseline + findings and Milestone 2 export scaffold ([#7](https://github.com/nmorgowicz-org/persona-forge/issues/7)) ([cdc75cf](https://github.com/nmorgowicz-org/persona-forge/commit/cdc75cfbee250cd73af02f5a91ff4def4aa715b8))
* **model:** remove unused debug hooks from transformers 5.x patches ([5e60279](https://github.com/nmorgowicz-org/persona-forge/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* release 0.10.0 ([#58](https://github.com/nmorgowicz-org/persona-forge/issues/58)) ([35b4cd9](https://github.com/nmorgowicz-org/persona-forge/commit/35b4cd947078f20788e9a4c367761ef0b6b5d3e2))
* release 0.11.0 ([#60](https://github.com/nmorgowicz-org/persona-forge/issues/60)) ([f8b7e5e](https://github.com/nmorgowicz-org/persona-forge/commit/f8b7e5e1a9ea3459ce253a522e4e9e33179acc71))
* release 0.11.1 ([#61](https://github.com/nmorgowicz-org/persona-forge/issues/61)) ([ed83e1a](https://github.com/nmorgowicz-org/persona-forge/commit/ed83e1aa7f309fa56f16cfc3a2e29f292d9e79f8))
* release 0.12.0 ([#65](https://github.com/nmorgowicz-org/persona-forge/issues/65)) ([9bf0848](https://github.com/nmorgowicz-org/persona-forge/commit/9bf084828f41baedc50921908500b502db1f19d8))
* release 0.13.0 ([#67](https://github.com/nmorgowicz-org/persona-forge/issues/67)) ([ddaa4bd](https://github.com/nmorgowicz-org/persona-forge/commit/ddaa4bdc68fecb2a6326a361dd979794df577354))
* release 0.14.0 ([#69](https://github.com/nmorgowicz-org/persona-forge/issues/69)) ([4489482](https://github.com/nmorgowicz-org/persona-forge/commit/448948224d5307819ddd43172c892578ddc8356d))
* release 0.15.0 ([#71](https://github.com/nmorgowicz-org/persona-forge/issues/71)) ([cd02c9d](https://github.com/nmorgowicz-org/persona-forge/commit/cd02c9d937acf38906dbc142a9e5a4fc80378c9e))
* release 0.15.1 ([#73](https://github.com/nmorgowicz-org/persona-forge/issues/73)) ([ccad823](https://github.com/nmorgowicz-org/persona-forge/commit/ccad8236ac55f7ea8f31562b07164bd47317eb89))
* release 0.16.0 ([#75](https://github.com/nmorgowicz-org/persona-forge/issues/75)) ([bc8f3f7](https://github.com/nmorgowicz-org/persona-forge/commit/bc8f3f70801cabc86d8b23be4301fc38c4cf6b90))
* release 0.16.1 ([#77](https://github.com/nmorgowicz-org/persona-forge/issues/77)) ([1e7baf8](https://github.com/nmorgowicz-org/persona-forge/commit/1e7baf82423fb80187ed70ab609c4d53af8d5cd2))
* release 0.17.0 ([#78](https://github.com/nmorgowicz-org/persona-forge/issues/78)) ([73eaa41](https://github.com/nmorgowicz-org/persona-forge/commit/73eaa416e19f112c128083135ddd0ee1732bc79d))
* release 0.17.1 ([#81](https://github.com/nmorgowicz-org/persona-forge/issues/81)) ([d01ff10](https://github.com/nmorgowicz-org/persona-forge/commit/d01ff10abbad787e8c45d5ec75620b1c78b19b3a))
* release 0.17.2 ([#83](https://github.com/nmorgowicz-org/persona-forge/issues/83)) ([dde2496](https://github.com/nmorgowicz-org/persona-forge/commit/dde24962ae1d0ffb7618e1126b4e43b8d767bdfc))
* release 0.17.3 ([#85](https://github.com/nmorgowicz-org/persona-forge/issues/85)) ([eb39d03](https://github.com/nmorgowicz-org/persona-forge/commit/eb39d03a90c511c53fce643beb60a95eabe6bab6))
* release 0.17.4 ([#87](https://github.com/nmorgowicz-org/persona-forge/issues/87)) ([1799f42](https://github.com/nmorgowicz-org/persona-forge/commit/1799f422433c51f3c401d7bc52984dbf76899bff))
* release 0.18.0 ([#89](https://github.com/nmorgowicz-org/persona-forge/issues/89)) ([3ae4813](https://github.com/nmorgowicz-org/persona-forge/commit/3ae481314cfd4a2409e3cf694ee260dd02b4e372))
* release 0.19.0 ([#90](https://github.com/nmorgowicz-org/persona-forge/issues/90)) ([f43d13c](https://github.com/nmorgowicz-org/persona-forge/commit/f43d13c92e5dac445e62c43b764e63cca5d0d580))
* release 0.2.0 ([#3](https://github.com/nmorgowicz-org/persona-forge/issues/3)) ([4a32a31](https://github.com/nmorgowicz-org/persona-forge/commit/4a32a31c9d5a3efe9298d88af4490083de79bcb3))
* release 0.20.0 ([#93](https://github.com/nmorgowicz-org/persona-forge/issues/93)) ([26392e2](https://github.com/nmorgowicz-org/persona-forge/commit/26392e223859ac89f1df9a60581578f9a5b3d31c))
* release 0.21.0 ([#95](https://github.com/nmorgowicz-org/persona-forge/issues/95)) ([6e0fe7c](https://github.com/nmorgowicz-org/persona-forge/commit/6e0fe7cd819db394a90ba77e12a4bbd3084d85a4))
* release 0.21.1 ([#100](https://github.com/nmorgowicz-org/persona-forge/issues/100)) ([1f76b6f](https://github.com/nmorgowicz-org/persona-forge/commit/1f76b6f4f355d1cb7ad50e2ab68e0c1de8bc2945))
* release 0.22.0 ([#102](https://github.com/nmorgowicz-org/persona-forge/issues/102)) ([fadda26](https://github.com/nmorgowicz-org/persona-forge/commit/fadda26fd0f0b9e6d9044f6b2802e64e83a22beb))
* release 0.22.1 ([#105](https://github.com/nmorgowicz-org/persona-forge/issues/105)) ([f2f747e](https://github.com/nmorgowicz-org/persona-forge/commit/f2f747e8f93e67c51e5266aa2d5ad4a40345e236))
* release 0.22.2 ([#109](https://github.com/nmorgowicz-org/persona-forge/issues/109)) ([0b012fa](https://github.com/nmorgowicz-org/persona-forge/commit/0b012fac953511d3f2db169c25f0f347827b8b89))
* release 0.22.3 ([#114](https://github.com/nmorgowicz-org/persona-forge/issues/114)) ([748f63e](https://github.com/nmorgowicz-org/persona-forge/commit/748f63e59a9a88d762baf37d66c0ad7cf9cd3e5d))
* release 0.23.0 ([#116](https://github.com/nmorgowicz-org/persona-forge/issues/116)) ([373f4da](https://github.com/nmorgowicz-org/persona-forge/commit/373f4daca3f5c6e7a788919b83d9129dd6636e12))
* release 0.3.0 ([#9](https://github.com/nmorgowicz-org/persona-forge/issues/9)) ([2299209](https://github.com/nmorgowicz-org/persona-forge/commit/2299209f7c0aacaf8709b970a37908b7358af724))
* release 0.3.1 ([#12](https://github.com/nmorgowicz-org/persona-forge/issues/12)) ([c304c39](https://github.com/nmorgowicz-org/persona-forge/commit/c304c39d1a0550c3c011ed6b414aa90081534c63))
* release 0.4.0 ([#15](https://github.com/nmorgowicz-org/persona-forge/issues/15)) ([ed5c5cc](https://github.com/nmorgowicz-org/persona-forge/commit/ed5c5cc3f410d35be111b5233c66cbfd288c4060))
* release 0.4.1 ([#17](https://github.com/nmorgowicz-org/persona-forge/issues/17)) ([51f7ec7](https://github.com/nmorgowicz-org/persona-forge/commit/51f7ec741030667a358769de837d29a0bdee1de0))
* release 0.4.2 ([#21](https://github.com/nmorgowicz-org/persona-forge/issues/21)) ([48d50f1](https://github.com/nmorgowicz-org/persona-forge/commit/48d50f173271e0c133ab1f08a6bea2247dc532f2))
* release 0.4.3 ([#23](https://github.com/nmorgowicz-org/persona-forge/issues/23)) ([fc0687d](https://github.com/nmorgowicz-org/persona-forge/commit/fc0687d89ae01671685cc97da3577a023bcdfdab))
* release 0.4.4 ([#25](https://github.com/nmorgowicz-org/persona-forge/issues/25)) ([88160a7](https://github.com/nmorgowicz-org/persona-forge/commit/88160a7ebf0b95fecde65296b3950685d41c3031))
* release 0.5.0 ([#28](https://github.com/nmorgowicz-org/persona-forge/issues/28)) ([77bb699](https://github.com/nmorgowicz-org/persona-forge/commit/77bb69926e79f47d512f2b8dc7138646403093bb))
* release 0.5.1 ([#30](https://github.com/nmorgowicz-org/persona-forge/issues/30)) ([4fe690b](https://github.com/nmorgowicz-org/persona-forge/commit/4fe690b0ff4dd2f74cbe47a2cfb7c942bc18ccb6))
* release 0.5.2 ([#32](https://github.com/nmorgowicz-org/persona-forge/issues/32)) ([c444db1](https://github.com/nmorgowicz-org/persona-forge/commit/c444db1de3a260340ff4b5d3a21a42fcf7b3fc06))
* release 0.5.3 ([#34](https://github.com/nmorgowicz-org/persona-forge/issues/34)) ([ae9a299](https://github.com/nmorgowicz-org/persona-forge/commit/ae9a299330927af3aab22fec1577c1b5f9c9f99c))
* release 0.5.4 ([#36](https://github.com/nmorgowicz-org/persona-forge/issues/36)) ([00ce55c](https://github.com/nmorgowicz-org/persona-forge/commit/00ce55c1d0e44fb7ecc367436b2b4f4de2843d26))
* release 0.6.0 ([#39](https://github.com/nmorgowicz-org/persona-forge/issues/39)) ([6e7c0a9](https://github.com/nmorgowicz-org/persona-forge/commit/6e7c0a96816919ad19e3d451f42cfc2e1f26e3d4))
* release 0.6.1 ([#41](https://github.com/nmorgowicz-org/persona-forge/issues/41)) ([1fe2f9c](https://github.com/nmorgowicz-org/persona-forge/commit/1fe2f9c8b8dc21550118bd6bf4fac8da716e6993))
* release 0.6.2 ([#43](https://github.com/nmorgowicz-org/persona-forge/issues/43)) ([bdd2d8f](https://github.com/nmorgowicz-org/persona-forge/commit/bdd2d8fe2e1221189f199f656d05891416b75e15))
* release 0.7.0 ([#45](https://github.com/nmorgowicz-org/persona-forge/issues/45)) ([c0486a8](https://github.com/nmorgowicz-org/persona-forge/commit/c0486a87ab60284d2a161bb38eb74b399cac86b2))
* release 0.7.1 ([#48](https://github.com/nmorgowicz-org/persona-forge/issues/48)) ([79f9341](https://github.com/nmorgowicz-org/persona-forge/commit/79f93418448d320d6a102f44fddb74df328d0bb8))
* release 0.8.0 ([#50](https://github.com/nmorgowicz-org/persona-forge/issues/50)) ([b2cdf9a](https://github.com/nmorgowicz-org/persona-forge/commit/b2cdf9a8bd452ba97fb1bf55c8ff7a0e0ad66043))
* release 0.9.0 ([#52](https://github.com/nmorgowicz-org/persona-forge/issues/52)) ([f224124](https://github.com/nmorgowicz-org/persona-forge/commit/f224124c7880e18f1df3e0e04aa3102849cf1f46))
* release 0.9.1 ([#55](https://github.com/nmorgowicz-org/persona-forge/issues/55)) ([8cda890](https://github.com/nmorgowicz-org/persona-forge/commit/8cda890cf4794fab032f53911c7fe40409b247a6))
* remove stale bench_results/ JSON files ([33fb4ea](https://github.com/nmorgowicz-org/persona-forge/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))

## [0.23.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.22.3...qwen3-tts-openvino-v0.23.0) (2026-07-09)


### Features

* **docker:** unified export service with EXPORT_TARGET=both for Base + VoiceDesign; simplified compose.yml and .env.example ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **frontend:** add Pocket TTS options and tuning controls to RuntimeConfigPage; PocketTTSWarningBanner for cloning unavailability ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** add MODEL_DTYPE control with backend-aware safety and bf16→float32 auto-correction on swap ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** add mount health checks (REF_AUDIO, /voices, /segments, HF cache, OV dir) and /health mount/pocket_tts reporting ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** integrate Pocket TTS as hotswappable backend with generation, voice states, and live knobs ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** register mounted REF_AUDIO as first-class "Mounted reference" voice; show "Mounted" badge in VoiceSelector ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** unify TTS_DIAG across backends and add watchdog with hard timeout; tighter pytorch+bf16 token cap; opt-in bf16→float32 auto-fallback ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))


### Bug Fixes

* **runtime:** gate bf16→float32 auto-fallback and cache fallback voice_state ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))
* **runtime:** gracefully handle missing faster_whisper instead of crashing at import ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))


### Code Refactoring

* **frontend:** centralize health, swap, runtime config, and speak-page state in Zustand store; refactor SpeakPage and useSwapStatus ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))


### Tests

* add test_pocket_tts_runtime and test_run_generate for watchdog/watchdog-regression and Pocket TTS behaviors ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))


### Documentation

* simplify ENV_REFERENCE and .env.example for new users; add pocket_tts_integration architecture doc ([30ac7be](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/30ac7befa4e849bc573a9e2b31eccb5cb6d4c4e3))


### Miscellaneous Chores

* **deps:** update node.js to cb4e8f7 ([#115](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/115)) ([06fd976](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/06fd976002d7707a4716fb060d83981455cbed7c))

## [0.22.3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.22.2...qwen3-tts-openvino-v0.22.3) (2026-07-07)


### Bug Fixes

* **ci:** correct release-please-action v4.4.1 SHA ([e6fc11f](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e6fc11f2d0eb37ab196dd28670db863a6161175b))
* **ci:** pin release-please to v4.4.1 (no parser bug), use rust release-type ([43e2d1b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/43e2d1bb3bc7b7c193c73ce10612044f3cbe9691))
* **ci:** restore original release-please workflow (remove permission overrides, v5.0.0) ([760acda](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/760acda24978dddb85c8be9ccf14bd0f4dc6d440))
* **ci:** restore release-please parsing and latest action ([de12867](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/de128675154a3240735cb45651f6af5e63fe89f1))
* **ci:** specify explicit permissions for release-please GitHub App token ([92a6745](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/92a674560e609355df3266d7059bd50e9a0fab2d))
* **ci:** specify explicit permissions for release-please GitHub App token ([#112](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/112)) ([627fb11](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/627fb11fe8835c39c880f09daa32e45e91868464))
* **ci:** use correct permission- prefix for release-please App token ([c08a6e6](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c08a6e62c041167198d588c8f70d7525b29b6eb8))
* **ci:** use correct permission- prefix for release-please App token ([d9b6f07](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d9b6f07acdf2612504ace26bc4043e23c2153d50))
* **ci:** use rust release-type like llama-monitor to avoid release creation error ([6cef070](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/6cef070450dcaed60209494eedb270519c7065ee))
* **ci:** use simple release-type (not rust) for Python project ([cf6a219](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/cf6a219d23ce3302b70fb2752b09dafa1369a8f8))
* **openvino:** auto-size OV_INFERENCE_THREADS from host core count ([de12867](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/de128675154a3240735cb45651f6af5e63fe89f1))


### Documentation

* correct Release Please commit override syntax ([de12867](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/de128675154a3240735cb45651f6af5e63fe89f1))


### Miscellaneous Chores

* **ci:** remove release-type from workflow ([c0c22af](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c0c22af22310c4abf9b316a816aadccc42841f5c))

## [0.22.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.22.1...qwen3-tts-openvino-v0.22.2) (2026-07-07)


### Miscellaneous Chores

* **deps:** update dependency pytest to v8.4.2 ([#106](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/106)) ([f09009e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/f09009e2414b2b20ee907c63957595fcb6a6b01a))
* **deps:** update dependency pytest to v9 ([#107](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/107)) ([cc9c593](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/cc9c593d8c978429a2a16bd265bba2e8b21f03f8))

## [0.22.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.22.0...qwen3-tts-openvino-v0.22.1) (2026-07-06)


### Miscellaneous Chores

* **deps:** update dependency shadcn to v4.13.0 ([#103](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/103)) ([b9126c8](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b9126c854bb9ceeb4bdd7fd271dbd4bcac98fc43))

## [0.22.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.21.1...qwen3-tts-openvino-v0.22.0) (2026-07-06)


### Features

* **audio_post:** add numpy-based compressor, loudness normalizer, crossfade concat, and drone-detect heuristic ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **frontend:** add AccentBank with regional accent examples and guidance ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **frontend:** add Persona Forge OmniVoice panel with accent chips, segment audition, and streaming results ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **frontend:** add standalone Stitch Studio page and Saved Segments browser to Voice Library ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **frontend:** add VST-style Stitch Timeline editor for per-clip trim/fade/gap controls and drag-and-drop reorder ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **openvino:** add OmniVoice accent-design engine with multi-candidate audition, segment library, and streaming progress API ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **runtime:** async OmniVoice job queueing when model is not yet loaded ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **runtime:** load Base model in background; allow /generate to queue through swaps instead of 503ing ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))


### Bug Fixes

* **frontend:** bound /health swap-status polling with timeout and exponential backoff ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **pytorch:** patch T5-generation prepare_inputs_for_generation, create_causal_mask, and sdpa_attention_forward for transformers 5.x ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))


### Documentation

* reorganize docs/plans into docs/dev with completed-feature rewrites; update all internal cross-references ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))


### Miscellaneous Chores

* **deps:** install OmniVoice from git (398b6113), faster-whisper, pydub; add ffmpeg; add segment library volume ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))
* **model:** remove unused debug hooks from transformers 5.x patches ([5e60279](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5e60279eb61fa1ce5aaa7a439ddb16781525fc4a))

## [0.21.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.21.0...qwen3-tts-openvino-v0.21.1) (2026-07-03)


### Bug Fixes

* **model:** correct seed max from 2^63-1 to 2^32-1 ([6748b8b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/6748b8bf4b622d024d059101ee7e942feff45959))


### Tests

* update voice design preset capacity to 360 ([6748b8b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/6748b8bf4b622d024d059101ee7e942feff45959))


### Documentation

* add conventional commit scopes to AGENTS.md ([6748b8b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/6748b8bf4b622d024d059101ee7e942feff45959))
* restore advanced env var detail in .env.example and HOW_TO_RUN.md ([6748b8b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/6748b8bf4b622d024d059101ee7e942feff45959))


### Miscellaneous Chores

* **deps:** pin dependencies ([#97](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/97)) ([035afc7](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/035afc7353f8a1604fad48a18cd36ac70d6869c8))

## [0.21.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.20.0...qwen3-tts-openvino-v0.21.0) (2026-07-02)


### Features

* **backend:** seeded VoiceDesign, per-voice cloning cache, runtime control panel ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **frontend:** complete VoiceDesign web UI ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **tests:** add Playwright E2E suite, screenshot harness, and dedicated UI CI workflow ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))


### Bug Fixes

* **deps:** rename requirements manifests for Dependabot graph compatibility ([9db3930](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/9db39308fd012e52e41cbf4cae73632d71184c0d))
* **tests:** repair CI test failures from stale fakes and pytest-only test module ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **tests:** silence werkzeug per-request access log in the E2E fake server ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))


### Documentation

* **agent-reference:** document delete/seed/runtime-config APIs, reorganize agent reference docs ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))

## [0.20.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.19.0...qwen3-tts-openvino-v0.20.0) (2026-07-02)


### Features

* add TTS_MAX_SPEECH_SECONDS for configurable stateful capacity ceiling ([47b2706](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/47b2706321d9fff7705b71f361aab90268c03508))

## [0.19.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.18.0...qwen3-tts-openvino-v0.19.0) (2026-07-02)


### Features

* **runtime:** add EOS conditioning fix, step-level diagnostics, and free-run handoff ([2092df3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))
* **runtime:** add TTS_MAX_NEW_TOKENS cap, TTS_NON_STREAMING override, and prompt diagnostics ([2092df3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))


### Bug Fixes

* drop cache_position from create_causal_mask for transformers 5.x ([b8901c9](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b8901c9646a9554e86df793911d5efdf0b4c0ccc))
* fix Dockerfile indentation for input_embeds patch ([3bf171f](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/3bf171f1508f84c50ecf0c53b3aa70e180f65f0b))
* patch codec_head.forward instead of replacing codec_head module ([9cc9863](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/9cc98630a9ce5dc52502ef9585cdfed30117ffcb))
* patch qwen-tts input_embeds -&gt; inputs_embeds for transformers 5.x ([8159e7d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8159e7d85821793ef9ea475670a4b79cc1e33dd0))
* **runtime:** fix transformers 5.x weight over-initialization randomizing talker embeddings and heads ([2092df3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))
* **runtime:** restore Mimi causal mask for correct reference codec tokens under transformers 5.x ([2092df3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))


### Miscellaneous Chores

* add codec_head logits diagnostic for decode-step debugging ([6df7709](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/6df7709c12e00e27ccb2e639fcd4cfbcd0be9c08))

## [0.18.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.4...qwen3-tts-openvino-v0.18.0) (2026-07-01)


### Features

* **runtime:** add decode-step heartbeat in OVStatefulCore ([5ea00db](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5ea00dbde2592d27a6d3682b9b776a1810855c0d))


### Bug Fixes

* **runtime:** force correct decode position_ids in OV cores ([5ea00db](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5ea00dbde2592d27a6d3682b9b776a1810855c0d))

## [0.17.4](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.3...qwen3-tts-openvino-v0.17.4) (2026-07-01)


### Bug Fixes

* **runtime:** suppress transformers 5.x deprecation warnings ([aea333a](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/aea333a7842c5af3884442a08050cdfce155d668))

## [0.17.3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.2...qwen3-tts-openvino-v0.17.3) (2026-07-01)


### Bug Fixes

* **runtime:** glibc malloc tuning for LOW_RAM_MODE; drop LD_PRELOAD ([85f2014](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/85f201445d28c8faceae9f7595d532fa99c85736))

## [0.17.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.1...qwen3-tts-openvino-v0.17.2) (2026-07-01)


### Bug Fixes

* **deps:** restore 'default' RoPE type removed in transformers 5.x ([d5f3ad5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d5f3ad5ff036d6bf6ef9e5898fea7930b8db5335))
* **runtime:** drop jemalloc from LOW_RAM_MODE; keep idle unload ([d5f3ad5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d5f3ad5ff036d6bf6ef9e5898fea7930b8db5335))

## [0.17.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.0...qwen3-tts-openvino-v0.17.1) (2026-07-01)


### Bug Fixes

* **deps:** restore 'default' RoPE type removed in transformers 5.x ([10c8a0c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/10c8a0c33f63a8394c7f74c69192e5c590a90445))

## [0.17.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.16.1...qwen3-tts-openvino-v0.17.0) (2026-07-01)


### Features

* **runtime:** log generation start, elapsed time, audio duration, and RTF ([8a65186](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8a6518691249cfccce0891ef70125400234d783b))


### Bug Fixes

* **deps:** patch qwen-tts pad_token_id access for transformers 5.x ([8a65186](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8a6518691249cfccce0891ef70125400234d783b))
* **deps:** patch qwen-tts pad_token_id access for transformers 5.x ([aa33890](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/aa33890aef859c7324bb821d42823576901fb9b0))

## [0.16.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.16.0...qwen3-tts-openvino-v0.16.1) (2026-07-01)


### Bug Fixes

* **deps:** add sox Python package to runtime deps ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** patch qwen-tts check_model_inputs for transformers 5.x API ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** remove check_model_inputs decorator instead of replacing it ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** remove qwen-tts from runtime.txt to resolve pip conflict ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** upgrade transformers to 5.12.1 to fix CVE-2026-1839 ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))

## [0.16.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.15.1...qwen3-tts-openvino-v0.16.0) (2026-07-01)


### Features

* **infra:** LOW_RAM_MODE with jemalloc allocator and entrypoint ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** expose OV_INFERENCE_THREADS; wire torch.set_num_threads to it ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** idle model unload with configurable cooldown and RAM telemetry ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** OpenVINO compiled kernel cache via OV_CACHE_DIR ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))


### Bug Fixes

* **compose:** default MODEL_SIZE to 1.7B to match recommendation ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))


### Documentation

* **compose:** explain :local tag vs production QWEN3_TTS_IMAGE usage ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **config:** group and expand .env.example with all user-facing vars ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* document idle unload, OV cache, and LOW_RAM_MODE ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* simplify README/HOW_TO_RUN; add RAM-tiered setup guidance ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* update AGENTS.md for single-image v0.15.1 ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))


### Miscellaneous Chores

* remove stale bench_results/ JSON files ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))

## [0.15.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.15.0...qwen3-tts-openvino-v0.15.1) (2026-07-01)


### Bug Fixes

* **ci:** publish one complete container image ([b7defd7](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b7defd7be16c6817713c162b88181fb3b77611b2))

## [0.15.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.14.0...qwen3-tts-openvino-v0.15.0) (2026-07-01)


### Features

* **runtime:** release PyTorch codec after startup to cut ~0.4 GiB RSS ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))


### Bug Fixes

* **runtime:** unbreak pytorch rollback, harden formats, doc memory root cause ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))


### Code Refactoring

* **config:** add MODEL_SIZE presets + apply_preset_env (validated) ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **service:** simplify runtime and local export ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **wip:** scaffold src/qwen3_tts package + write simplify-v2 HANDOFF ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))


### Documentation

* record codec-release A/B, reject INT8 vocoder, slim HANDOFF ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* refresh README + HOW_TO_RUN with 1.7B recommendation, footprint, codec flag ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** correct memory root cause with measured data; rollback confirmed ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record generation-peak A/B (0.6B vs 1.7B nearly identical) ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record listening preference ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record simplify-v2 validation ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))

## [0.14.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.13.0...qwen3-tts-openvino-v0.14.0) (2026-06-30)


### Features

* **api:** add OpenAI-compatible /v1/audio/speech endpoint ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **runtime:** identical-seed batch vs streaming latency comparison ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))


### Bug Fixes

* **serve:** drop gunicorn --preload from single-worker model server ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))


### Documentation

* **handoff:** record Task 4/5 progress and OpenAI endpoint ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **plans:** hermes TTS integration analysis and OpenAI-endpoint plan ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **plans:** record server-side voice decision and ref_audio reality ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* record streaming listening verdict (identical, no seam) ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **results:** record completed transport and rollback tests ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **results:** record Task 3 per-core overlap go/no-go and preload fix ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **results:** record v0.13.0 baked-image streaming validation ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **run:** document no-preload memory fix and revised 1.7B footprint ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))

## [0.13.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.12.0...qwen3-tts-openvino-v0.13.0) (2026-06-30)


### Features

* **runtime:** stream OpenVINO vocoder PCM during generation ([d67a505](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))


### Bug Fixes

* **runtime:** honor BF16 serving load settings in app_worker ([d67a505](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))


### Tests

* **runtime:** validate streaming code capture and transport parity ([d67a505](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))


### Documentation

* **runtime:** record streaming results and operator runbook ([d67a505](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))

## [0.12.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.11.1...qwen3-tts-openvino-v0.12.0) (2026-06-29)


### Features

* **export:** infer stateful IR layout and record artifact provenance ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **health:** report active stateful cores and cache capacities ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **runtime:** add stateful KV cache support for the 0.6B main and predictor cores ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))


### Tests

* **runtime:** cover stateful predictor generation-step defaults ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))


### Documentation

* **results:** record 0.6B stateful footprint and quality gates ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))

## [0.11.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.11.0...qwen3-tts-openvino-v0.11.1) (2026-06-29)


### Documentation

* mark M9 closed and shipped in v0.11.0; refresh handoff next steps ([d2dc334](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d2dc334fa974d109e2a588816d799aff7d481cf4))

## [0.11.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.10.0...qwen3-tts-openvino-v0.11.0) (2026-06-29)


### Features

* **m9:** add exact ru_maxrss per-phase attribution to find the generation transient$'\n\n'feat(m9): localize lifetime peak to PyTorch model-load transient$'\n\n'feat(m9): bf16 serving load to eliminate the fp32 load-transient boot spike ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** add pytorch-vs-stateful parity mode to test_stateful_main_parity ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** add static stateful main cache spike with parity test ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** FP32-vs-PyTorch parity (0.6B) and per-mode max_abs tolerance ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** reduce 1.7B generation memory with stateful main cache and early PyTorch weight release ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** wire OPENVINO_MAIN_STATEFUL_MODEL and OPENVINO_RELEASE_TORCH in app_worker ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Bug Fixes

* **ci:** install NumPy for dump-audio unit tests ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** clean up _OVStatefulCore delegation and accept generation_steps ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** fail-closed startup when OPENVINO_RELEASE_TORCH=1 ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **release:** preserve every commit override entry ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Performance Improvements

* **m9:** release PyTorch weights before main-graph compile ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Documentation

* **m9:** correct lifetime-peak root cause and refocus next steps on measuring it ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** listening check passed; update M9 gates status ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** record bf16 serving result (lifetime peak 11.6 to 8.3 GiB)$'\n\n'docs(m9): record bf16 quality-equivalent verdict; bf16 serving adopted$'\n\n'feat(serving): capacity-768 stateful main, silence trim, capacity-tuning docs ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** record M9 gate results (capacity, latency, concurrency, rollback) ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Miscellaneous Chores

* **m9:** drop committed raw RSS profile and reject raw profiles in repo guard ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))

## [0.10.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.9.1...qwen3-tts-openvino-v0.10.0) (2026-06-29)


### Features

* **runtime:** release PyTorch core weights post-install (M7 memory) ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **export:** add INT4 precision-tagged artifact directories and document M7-M9 findings ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **bench:** add measured 1.7B speed gate (M1.7B-A), with INT4 reaching 1.35x ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))

### Documentation

* **m7:** document OPENVINO_RELEASE_TORCH and OpenVINO-only validation ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **m5:** record 1.7B INT4 results and the stateful-cache design ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **handoff:** add a self-contained next-agent brief ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))

## [0.9.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.9.0...qwen3-tts-openvino-v0.9.1) (2026-06-29)


### Bug Fixes

* **export:** reject unsupported INT8 calibration ([08e1c58](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08e1c58c0413596fa10d75ffb6a435ede4021662))

## [0.9.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.8.0...qwen3-tts-openvino-v0.9.0) (2026-06-29)


### Features

* **export:** data-aware INT8 calibration (scale_estimation) scaffold ([8739289](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/87392896d8db155ea541ad8cc70251926c4e429b))


### Bug Fixes

* **runtime:** resolve vocoder IR filename; add per-core precision + audio dump ([8739289](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/87392896d8db155ea541ad8cc70251926c4e429b))
* **vocoder:** actually wire the OpenVINO vocoder + add backend provenance ([8739289](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/87392896d8db155ea541ad8cc70251926c4e429b))

## [0.8.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.7.1...qwen3-tts-openvino-v0.8.0) (2026-06-29)


### Features

* **runtime:** add run_bench.sh for simpler harness invocation ([0e3d13c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))
* **runtime:** improve test_ov_generation.py reporting and output path safety ([0e3d13c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))


### Bug Fixes

* **runtime:** include ov_vocoder_runtime.py in runtime image ([0e3d13c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))

## [0.7.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.7.0...qwen3-tts-openvino-v0.7.1) (2026-06-28)


### Bug Fixes

* **runtime:** exclude internal 'vocoder' key from OpenVINO CPU compile_model config ([5d56038](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5d56038c8d35f219e3ced4672392e71628b784fa))

## [0.7.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.6.2...qwen3-tts-openvino-v0.7.0) (2026-06-28)


### Features

* **m4:** buffer-backed K/V cache with OPENVINO_BUFFER_KV guard and bench env helper ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **m4:** wire OpenVINO vocoder IR into the runtime with PyTorch fallback ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))


### Bug Fixes

* **runtime:** correct _single_chunk left-context warmup and return types; add fallback warnings ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **runtime:** correct vocoder IR 2D/3D shape unpack in _run_ir ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **runtime:** correct vocoder multi-chunk waveform slicing and tensor copy ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **test:** harden code normalization, seed greedy runs, gc for mode=all, add entropy metric ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))

## [0.6.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.6.1...qwen3-tts-openvino-v0.6.2) (2026-06-28)


### Bug Fixes

* **harness:** correct frame/codebook axes in M4 code comparison ([d7136c4](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d7136c4c4ef99f5cbe762ecad6879db0ede9ccc5))

## [0.6.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.6.0...qwen3-tts-openvino-v0.6.1) (2026-06-28)


### Bug Fixes

* **ci:** make Dockerfile COPY-line check robust to additional files ([5717ddb](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))
* **docker:** include ov_runtime_config, ov_talker_runtime, bench_common, test_ov_generation in build ([5717ddb](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))
* **scripts:** default M4 reference WAV to persistent project-owned path on docker-agent ([5717ddb](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))

## [0.6.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.4...qwen3-tts-openvino-v0.6.0) (2026-06-28)


### Features

* **export:** relax provenance fields to best-effort non-blocking defaults ([e9d9943](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **runtime:** add M4 OpenVINO talker runtime with explicit K/V cache, persistent InferRequests ([e9d9943](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **test:** add generation-level parity harness (code agreement, waveform SNR, latency/RTF) ([e9d9943](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))

## [0.5.4](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.3...qwen3-tts-openvino-v0.5.4) (2026-06-28)


### Bug Fixes

* **ci:** authenticate and reduce Docker Hub pulls in image validation ([b320f0d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))
* **ci:** retain reliable GHCR cleanup with 15 versions ([b320f0d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))
* **export:** correct INT8 mode selection and make transformer parity fail closed ([b320f0d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))

## [0.5.3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.2...qwen3-tts-openvino-v0.5.3) (2026-06-28)


### Bug Fixes

* **ci:** use curl instead of gh in GHCR cleanup (gh not installed on runner) ([794df6c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/794df6cd390b5577a34a1b07ec6f0a03c0e9c5e3))

## [0.5.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.1...qwen3-tts-openvino-v0.5.2) (2026-06-28)


### Bug Fixes

* **ci:** tag-aware GHCR cleanup preserves protected image versions ([95ca024](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/95ca024267415ed1688758b9cdce664f9bbfb207))

## [0.5.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.0...qwen3-tts-openvino-v0.5.1) (2026-06-28)


### Bug Fixes

* **export:** respect NNCF INT8 constraints (no group_size/ratio overrides) ([0d7ce4f](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/0d7ce4f90b67eb58a063827f87fa14c813806731))

## [0.5.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.4...qwen3-tts-openvino-v0.5.0) (2026-06-28)


### Features

* **runtime:** wire INT8 tuning, parity gates, and TTS_BACKEND selection ([2ecf8e3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2ecf8e3ddc3d28aff99de9aa7a8679c75b253eb8))

## [0.4.4](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.3...qwen3-tts-openvino-v0.4.4) (2026-06-28)


### Bug Fixes

* **export:** patch DynamicLayer.lazy_initialization to fix OV aten::cat rank error ([aebce00](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/aebce0047693a92202a5c6b9bcf312db73736ee0))

## [0.4.3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.2...qwen3-tts-openvino-v0.4.3) (2026-06-28)


### Bug Fixes

* **ci:** add no-cache dispatch input to recover from broken GHCR build cache ([e68eb16](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e68eb1679a566c4a7a2d5eca706103484d77bb6f))

## [0.4.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.1...qwen3-tts-openvino-v0.4.2) (2026-06-28)


### Bug Fixes

* **ci:** broaden ignore-versions to protect all runtime/exporter/buildcache tags ([5340067](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5340067f52f012a87a8498499c593c7ab634526f))
* **export:** use rank-4 empty tensor in DynamicLayer to fix OV aten::cat rejection ([5340067](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5340067f52f012a87a8498499c593c7ab634526f))

## [0.4.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.0...qwen3-tts-openvino-v0.4.1) (2026-06-28)


### Bug Fixes

* **export:** pre-build 4D causal mask to prevent static kv_length in decode IR ([#16](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/16)) ([10b2260](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/10b2260a6a7371ee20aca9926124d45622fb8eda))

## [0.4.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.3.1...qwen3-tts-openvino-v0.4.0) (2026-06-28)


### Features

* **export:** add Milestone 2 transformer core parity gate for main and predictor cores ([fc527f5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/fc527f5263bb553f462755bcab999fbf3300a200))
* **export:** complete Milestone 1.5 vocoder decoder export, parity gate, and benchmark ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))


### Bug Fixes

* **export:** require SOURCE_COMMIT and EXPORTER_IMAGE_DIGEST provenance env vars ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** resolve loaded vocoder decoder access path ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** supply traceable causal and sliding-window attention masks ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** trace with eager attention on nested configs ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** use fixed 325-frame vocoder input contract ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))

## [0.3.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.3.0...qwen3-tts-openvino-v0.3.1) (2026-06-28)


### Bug Fixes

* **ci:** publish images only from Release Please tags ([bec5163](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/bec516367a4a31a778a6ffcb744d7c50e028f69d))
* **export:** include the OpenVINO export CLI in the exporter image ([bec5163](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/bec516367a4a31a778a6ffcb744d7c50e028f69d))

## [0.3.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.2.0...qwen3-tts-openvino-v0.3.0) (2026-06-28)


### Features

* **export:** add vocoder decoder export as Milestone 1.5 ([2bff1da](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2bff1da1ed88aeb9543b280714e4a55eeb6298eb))
* **export:** Milestone 1.5 vocoder decoder export + fix CI exporter smoke test ([#10](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/10)) ([d2b9649](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d2b964936264d8c9c2698b20d030257a67abf358))

## [0.2.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.1.0...qwen3-tts-openvino-v0.2.0) (2026-06-28)


### Features

* bootstrap configurable OpenVINO TTS service ([#1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/1)) ([8eaea24](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8eaea2491cc7a339671f020903115068eecdd121))


### Bug Fixes

* **ci:** add .release-please-manifest.json required by release-please v17 ([#2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/2)) ([97c3bee](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/97c3bee81b99f284c369008a6ee2c930a39ad078))
* **ci:** remove unsupported pull-request-header and align version to 0.2.0 ([bf3578e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/bf3578ef7929477249a1c80e65d90e36c4548664))
