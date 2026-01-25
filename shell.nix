{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    glfw
    libGL
    xorg.libX11
    wayland
    
    (python3.withPackages (ps: with ps; [
      evdev
      numpy
      pyyaml
      moderngl
      glfw
    ]))
  ];

  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.glfw}/lib:${pkgs.libGL}/lib:${pkgs.wayland}/lib:${pkgs.libxkbcommon}/lib:$LD_LIBRARY_PATH
    sudo chmod o+r /dev/input/event*
    echo "Bongo Cat"
  '';
}
