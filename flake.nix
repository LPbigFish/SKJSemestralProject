{
  description = "Description for the project";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
        "x86_64-darwin"
      ];
      perSystem =
        {
          pkgs,
          ...
        }:
        let
          python3 = pkgs.python3.override {
            self = python3;
            packageOverrides = pyfinal: pyprev: {
              # Override example VVV
              # mathgenerator = pyfinal.callPackage ./mathgenerator.nix { };
            };
          };
          python = python3.withPackages (
            p: with p; [
              fastapi
              fastapi-cli
              pip
              pytest
              sqlalchemy
              pydantic
              python-multipart
              aiofiles
              aiosqlite
              uvicorn
              alembic
              pytest-asyncio
              msgpack
            ]
          );
        in
        {
          devShells.default = pkgs.mkShell {
            buildInputs = [
              python
              pkgs.sqlite
              pkgs.pyright
            ];
          };
        };
    };
}
