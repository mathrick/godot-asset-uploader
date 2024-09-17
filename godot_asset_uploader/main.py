import click

from . import vcs, config
from .markdown import Renderer, Document

@click.command()
@click.option("--readme", default="README.md", help="Location of README file, relative to project root")
@click.option("--changelog", default="CHANGELOG.md", help="Location of changelog file, relative to project root")
@click.argument("root", default=".")
def main(root, readme, changelog):
    """Automatically upload or update an asset in Godot Asset Library
based on the project repository.

ROOT should be the root of the project, meaning a directory containing
the file 'gdasset.ini', or a VCS repository (currently, only Git is
supported). If not specified, it will be determined automatically,
starting at the current directory."""
    project_root = vcs.get_project_root(root)
    cfg = config.Config(
        readme=project_root / readme,
        changelog=changelog and project_root / changelog
    )
    with open(readme) as input:
        with Renderer(cfg, max_line_length=None) as renderer:
            rendered = renderer.render(Document(input))
            print(rendered)

if __name__ == "__main__":
    main()
