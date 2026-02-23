{ pkgs, lib, config, inputs, ... }:
{ packages = [
    pkgs.git
    pkgs.git-lfs
  ];

  languages.python = {
    enable = true;
    venv = {
      enable = true;
      requirements = ''
         numpy
         pyright
         pytest
         -e ./
      '';
    };
  };

  git-hooks = {
    default_stages = [ "commit" ];
    hooks = {
      pyright = {
        enable = true;
        description = "Run pyright type checker on InternalSimulator package";
        entry = "pyright --project ./pyrightconfig.json";
        files = "\\.py$";
        pass_filenames = false;
      };
    };
  };
}
