# The package this repository builds. The suites that judge it live in
# `nix/checks.nix`, which declares its own inputs, so nothing that only a test
# needs is named here.
#
# Nothing else belongs in this repository: the dev shell and the collection
# that assembles this with its siblings live in pyterm.
#
# **This is a pyproject.nix builders package, not a nixpkgs one.** The
# renderer reads `pyproject.toml`, and an environment is a virtualenv rather
# than a PYTHONPATH. Lillecarl/pymux#319.
#
# **`pyproject.toml` is upstream's and this file does not touch it.** Every
# patch to this repository has to be one upstream could take, and neither a
# build-system swap nor an extra that only our checks read is such a patch.
# So the version, the dependency and the setuptools backend are read as
# upstream wrote them, and what the suites need is named below in Nix. That
# is the one place this recipe differs from its four siblings, where the
# `test` extra lives in `pyproject.toml`.
{
  lib,
  stdenv,
  python,
  pyprojectHook,
  resolveBuildSystem,
  mkVirtualEnv,
  mkProject,
  callPackage,
}:
let
  # What the wheel is built from, and nothing else. This repository is 32M:
  # `docs`, `examples`, `tools` and a CHANGELOG, none of which the package
  # needs, and a `__pycache__` beside every module that a local run rewrites.
  # A source that a test run changes rebuilds everything above it.
  # Lillecarl/pymux#320.
  projectRoot = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      # Not only the `.py` files: `py.typed` is what tells a checker that
      # the annotations here are meant to be read.
      (lib.fileset.fileFilter (file: file.hasExt "py" || file.name == "py.typed") ./src)
      ./pyproject.toml
      ./README.rst
      ./LICENSE
    ];
  };

  package =
    (mkProject {
      inherit projectRoot python;
      extra = rendered: {
        passthru = rendered.passthru // { inherit checks; };

        meta = rendered.meta // {
          description = "Library for building powerful interactive command line applications";
          homepage = "https://github.com/prompt-toolkit/python-prompt-toolkit";
          license = lib.licenses.bsd3;
        };
      };
    })
      {
        inherit stdenv pyprojectHook resolveBuildSystem;
      };

  # Only the tests, not the whole repository. A copy of everything makes
  # the test run rebuild on every unrelated edit.
  #
  # It is built here and not in `nix/checks.nix`, because `./.` there is the
  # `nix` directory and this needs the root of the repository.
  testSources = lib.fileset.toSource {
    root = ./.;
    fileset = ./tests;
  };

  # What the suite runs on: prompt-toolkit, what it declares, and pytest.
  #
  # pytest is named here and not in a `test` extra, because `pyproject.toml`
  # is upstream's. So this is the one list of this kind in the collection
  # that a reader has to find in a `.nix` file, and the reason is written at
  # the top of this one.
  testEnv = mkVirtualEnv "prompt-toolkit-test-env" {
    prompt-toolkit = [ ];
    pytest = [ ];
  };

  checks = callPackage ./nix/checks.nix { inherit testEnv testSources; };
in
package
