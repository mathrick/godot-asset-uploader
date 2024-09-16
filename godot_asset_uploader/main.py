import click

from . import vcs, config
from .markdown import Renderer, Document

@click.command()
@click.option("--readme", default="README.md")
@click.option("--changelog", default="CHANGELOG.md")
@click.argument("root", default=".")
def main(root, readme, changelog):
    """Automatically upload or update an asset in Godot Asset Library
based on the project repository"""
    project_root = vcs.get_project_root(root)
    cfg = config.Config(
        readme=project_root / readme,
        changelog=changelog and project_root / changelog
    )
    with open(readme) as input:
        with Renderer(cfg, max_line_length=200) as renderer:
            rendered = renderer.render(Document(input))
            print(rendered)

if __name__ == "__main__":
    main()
