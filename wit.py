import os
import shutil
import sys
from typing import Any, Callable, Dict, Optional

import matplotlib.pyplot as plt  # type: ignore
import networkx as nx  # type: ignore

from hashing import Hashing
from witmanager import _logger, WitEditor, WitStatus


def init() -> None:
    """Create the directories for the images."""
    current_dir = os.getcwd()
    WitEditor.create_dirs(os.path.join(current_dir, '.wit', 'images'))
    WitEditor.create_dirs(
        os.path.join(current_dir, '.wit', 'staging_area'), f=os.mkdir
    )
    wit = WitEditor()
    wit.update_activated_branch('master')


def add(path: str) -> None:
    """Add the path directories and files into the backup directory."""
    wit = WitEditor(path)

    if os.path.isfile(wit.real_path):
        rel_path = os.path.relpath(
            os.path.dirname(wit.real_path), wit.parent_wit_dir
        )
    else:
        rel_path = os.path.relpath(wit.real_path, wit.parent_wit_dir)

    if rel_path == '.':
        final_dir = wit.stage_dir
    else:
        final_dir = os.path.join(wit.stage_dir, rel_path)
        wit.create_dirs(final_dir)

    if os.path.isdir(wit.real_path):
        wit.copy_tree(
            src=wit.real_path, dst=wit.stage_dir, rel=wit.parent_wit_dir
        )
    else:
        shutil.copy2(wit.real_path, final_dir)
    _logger.info('%s has been added to the stage backup', wit.real_path)


def commit(message: str, branch_id: Optional[str] = None) -> None:
    """Commit a new request for a backup."""
    wit = WitEditor()

    commit_id = Hashing.by_path(wit.stage_dir)
    commit_id_images_dir = os.path.join(wit.images_dir, commit_id)
    try:
        os.mkdir(commit_id_images_dir)
    except FileExistsError:
        _logger.exception(
            'The %s image had already been committed', commit_id
        )
    else:
        wit.create_metadata_file(message, commit_id, branch_id)
        wit.image_copy_files(commit_id_images_dir)

        wit.update_references_file(commit_id)
        _logger.info(
            'Commit %s has been created', commit_id
        )


def status() -> None:
    """Return the status of the wit project."""
    wit = WitStatus()

    print(f'Commit ID: {wit.last_commit_id}')

    if wit.last_commit_id:
        full_changes = wit.get_changes_to_be_committed()
        print(f'Changes to be committed: {", ".join(full_changes)}')

        changed, untracked = wit.compare_two_list_files(
            wit.original_files, wit.stage_files,
            wit.parent_wit_dir, wit.stage_dir
        )
        print(f'Changes not staged for commit: {", ".join(changed)}')
        print(f'Untracked files: {", ".join(untracked)}')


def checkout(commit_id: str) -> None:
    """Checkout the image commit_id to the real directory."""
    wit = WitEditor()
    wit_status = WitStatus()

    changes_to_be_committed = wit_status.get_changes_to_be_committed()
    changed, untracked = wit_status.compare_two_list_files(
        wit_status.original_files, wit_status.stage_files,
        wit_status.parent_wit_dir, wit.stage_dir
    )
    if changed or changes_to_be_committed:
        _logger.warning(
            'There are changed files which have not been committed, '
            'commit them first: %s',
            ', '.join(changed + changes_to_be_committed)
        )
    else:
        is_branch = False
        if commit_id in wit.get_all_branches()[1:]:   # Without 'HEAD' line
            wit.update_activated_branch(commit_id)
            commit_id = wit.get_commit_id(f'{commit_id}=')
            is_branch = True
        commit_id_images_dir = os.path.join(wit.images_dir, commit_id)

        # Changing the original path content
        wit.copy_tree(
            src=commit_id_images_dir, dst=wit.parent_wit_dir,
            rel=commit_id_images_dir, ignore_files=untracked
        )

        # Changing the stage content
        shutil.rmtree(wit.stage_dir)
        os.mkdir(wit.stage_dir)
        wit.copy_tree(
            src=commit_id_images_dir, dst=wit.stage_dir,
            rel=commit_id_images_dir
        )
        wit.update_references_file(commit_id, is_branch)
        _logger.info(
            'HEAD part had updated successfully to: %s, '
            'contents had successfully changed', commit_id
        )


def graph(param: Optional[str] = None) -> None:
    wit = WitStatus()

    plt.figure(figsize=(15, 8))
    branches_colors = {
        branch: 'w'
        for branch in wit.get_all_branches()
    }

    G = nx.DiGraph(directed=True)

    if param and param != '--all':
        _logger.warning(
            'The function can get only two options: '
            'without arguments, or with --all argument.'
        )
    else:
        tree_graph = list(wit.build_graph_tree(param).items())
        final_tree_graph = list(wit.build_graph_items(tree_graph))
        G.add_edges_from(final_tree_graph)
        G.remove_node('None')

        node_colors = [
            branches_colors.get(node, 'dodgerblue') for node in G.nodes()
        ]
        options = {
            'node_size': 2000,
            'node_color': node_colors,
            'font_size': 6,
            'font_color': 'firebrick',
            'width': 2,
            'arrowstyle': '-|>',
            'arrowsize': 6,
        }
        nx.draw_networkx(G, arrows=True, **options)
        plt.show()


def branch(name: str) -> None:
    wit = WitEditor()

    wit.update_new_branch(name)
    _logger.info(
        'The branch %s has been created', name
    )


def merge(branch_name: str) -> None:
    wit = WitEditor()
    wit_status = WitStatus()

    if branch_name in wit_status.get_all_branches()[1:]:
        branch_commit_id = wit_status.get_commit_id(line=f'{branch_name}=')
    else:
        branch_commit_id = branch_name

    ancestor = wit_status.get_lowest_common_ancestor(branch_commit_id)
    ancestor_dir = os.path.join(wit_status.images_dir, ancestor)
    branch_dir = os.path.join(wit_status.images_dir, branch_commit_id)

    ancestor_files = wit_status._get_files(files=ancestor_dir)
    branch_files = wit_status._get_files(files=branch_dir)

    changed_branch, untracked_branch = wit_status.compare_two_list_files(
        branch_files, ancestor_files,
        branch_dir, ancestor_dir
    )
    changed_head, untracked_head = wit_status.compare_two_list_files(
        wit_status.commit_id_files, ancestor_files,
        wit_status.commit_id_dir, ancestor_dir
    )

    both_changed = set.intersection(set(changed_branch), set(changed_head))
    both_untracked = set.intersection(
        set(untracked_branch), set(untracked_head)
    )
    are_all_ok = wit_status.check_all_changed_files(
        both_changed, both_untracked, branch_dir, ancestor_dir
    )

    if are_all_ok:
        immediately_files = [
            filename
            for filename in changed_branch
            if filename not in both_changed
        ] + untracked_branch
        for file in immediately_files:
            file_dir = os.path.join(branch_dir, file)
            final_dir = os.path.join(wit_status.stage_dir, file)
            if not os.path.isdir(os.path.dirname(final_dir)):
                wit.create_dirs(os.path.dirname(final_dir))
            shutil.copy2(file_dir, final_dir)

        for file in both_changed:
            file_merge_content = wit_status.file_after_merge(
                file, branch_dir, wit_status.commit_id_dir, ancestor_dir
            )
            final_dir = os.path.join(wit_status.stage_dir, file)
            if not os.path.isdir(os.path.dirname(final_dir)):
                wit.create_dirs(os.path.dirname(final_dir))
            with open(final_dir, 'w') as new_file:
                new_file.write(file_merge_content)

        _logger.info('The branch %s had been merged successfully', branch_name)
        commit(message=f'Merge with {branch_name}', branch_id=branch_commit_id)

    else:
        _logger.warning(
            'There are files that have changed in both branches in '
            'different lines'
        )


if __name__ == '__main__':
    FUNCTIONS: Dict[str, Callable[..., Any]] = {
        'init': init, 'add': add, 'commit': commit,
        'status': status, 'checkout': checkout, 'graph': graph,
        'branch': branch, 'merge': merge,
    }
    func, args = sys.argv[1], sys.argv[2:]
    FUNCTIONS[func](*args)
