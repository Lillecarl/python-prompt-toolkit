# The package this repository builds. The suites that judge it live in
# `nix/checks.nix`, which declares its own inputs, so nothing that only a test
# needs is named here.
#
# Nothing else belongs in this repository: the dev shell and the collection
# that assembles this with its siblings live in pyterm.
{
  lib,
  buildPythonPackage,
  setuptools,
  wcwidth,
  callPackage,
}:
let
  package = buildPythonPackage {
    pname = "prompt-toolkit";
    version = "3.0.52";
    src = lib.cleanSource ./.;
    pyproject = true;

    build-system = [ setuptools ];
    dependencies = [ wcwidth ];

    # The suite runs as `checks.unit`, against the installed package.
    doCheck = false;
    pythonImportsCheck = [ "prompt_toolkit" ];

    passthru = { inherit checks; };

    meta = {
      description = "Library for building powerful interactive command line applications";
      homepage = "https://github.com/prompt-toolkit/python-prompt-toolkit";
      license = lib.licenses.bsd3;
    };
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

  checks = callPackage ./nix/checks.nix { inherit package testSources; };
in
package
