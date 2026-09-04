# The package this repository builds. Nothing else belongs here: the dev shell
# and the collection that assembles this with its siblings live in pyterm.
{
  lib,
  buildPythonPackage,
  setuptools,
  wcwidth,
}:
buildPythonPackage {
  pname = "prompt-toolkit";
  version = "3.0.52";
  src = lib.cleanSource ./.;
  pyproject = true;

  build-system = [ setuptools ];
  dependencies = [ wcwidth ];

  pythonImportsCheck = [ "prompt_toolkit" ];

  meta = {
    description = "Library for building powerful interactive command line applications";
    homepage = "https://github.com/prompt-toolkit/python-prompt-toolkit";
    license = lib.licenses.bsd3;
  };
}
