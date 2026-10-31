"""Select explicit developer linkage or a portable release bundle."""
def configure_source_marker(resources,project,release):
    marker=resources/'source-project.txt'
    if release:marker.unlink(missing_ok=True)
    else:marker.write_text(str(project),encoding='utf8')
