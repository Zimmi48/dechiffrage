{
  description = "MIDI piano validator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    mirpkgs.url = "github:carlthome/mirpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, mirpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };

        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          mido
          python-rtmidi
        ]);

        music21 = mirpkgs.packages.${system}.music21.overrideAttrs (_: { doInstallCheck = false; });
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            music21
            pkgs.alsa-utils
          ];

          shellHook = ''
            echo "MIDI piano validator ready."
            echo "Run: python validator_progression.py"
          '';
        };
      }
    );
}