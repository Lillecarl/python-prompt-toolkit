# The suites that judge prompt-toolkit.
#
# It declares its own inputs, so `default.nix` holds the package and does not
# carry arguments that only a test needs.
#
# `package` and `testSources` come from `default.nix`: the first because a
# suite runs against the installed package, the second because it knows where
# the repository root is and this file does not.
#
# `nix/suite.nix` says why a check is two derivations.
{
  python,
  pytest,
  callPackage,
  package,
  testSources,
}:
let
  inherit (callPackage ./suite.nix { }) suite;

  pythonWithTests = python.withPackages (ps: [
    package
    pytest
  ]);

  prepare = ''
    cp -r ${testSources}/tests .
    chmod -R +w .
    export HOME="$TMPDIR"
    export LANG=C.UTF-8
    export PYTHONDONTWRITEBYTECODE=1
  '';

  # What pytest runs, for instance
  # `PROMPT_TOOLKIT_TESTS=tests/test_layout.py nix build --file . checks.prompt-toolkit-unit`.
  #
  # It reaches the evaluation through the environment, which works because a
  # build from a file evaluates impurely. A flake would see nothing here.
  selection =
    let
      value = builtins.getEnv "PROMPT_TOOLKIT_TESTS";
    in
    if value == "" then "tests" else value;
in
{
  unit = suite {
    name = "prompt-toolkit-unit";
    inputs = [ pythonWithTests ];
    setup = prepare;
  } "python -m pytest ${selection} -q -p no:cacheprovider";
}
