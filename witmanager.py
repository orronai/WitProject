from collections import defaultdict
from datetime import datetime
import fnmatch
import logging
import os
import shutil
from time import gmtime, strftime
from typing import (
    Callable, DefaultDict, Iterable, Iterator,
    List, Optional, Tuple, Union,
)

from hashing import Hashing


# Constants
Text = Union[str, bytes]
COMMIT_ID_LENGTH: int = 40

# logging configurations
logging.basicConfig(level=logging.INFO,
                    format=(
                        '%(asctime)s %(name)-10s %(levelname)-12s %(message)s'
                    ),
                    datefmt='%Y-%m-%d %H:%M',
                    filename=os.path.join(
                        f'{os.path.dirname(os.path.abspath(__file__))}',
                        'logfile.log'
                    ),
                    filemode='a'
                    )
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)-10s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)
_logger = logging.getLogger(__file__)


class WitManager:
    def __init__(self, path: str = ''):
        self.current_dir = os.getcwd()
        self.real_path = self._get_real_path(path)
        self.parent_wit_dir = self._get_first_wit_dir(self.real_path)
        self.wit_dir = self._get_wit_dir()
        self.stage_dir = self._get_stage_dir()
        self.images_dir = self._get_images_dir()
        self.references_path = os.path.join(self.wit_dir, 'references.txt')
        self.activated_path = os.path.join(self.wit_dir, 'activated.txt')

    def _get_first_wit_dir(self, path: str) -> str:
        if os.path.isfile(path):
            return self._get_first_wit_dir(os.path.dirname(path))
        if '.wit' in os.listdir(path):
            return path
        if os.path.ismount(path):
            _logger.exception(
                "There isn't any .wit directory in the %s path", self.real_path
            )
            raise FileNotFoundError(
                "There isn't any .wit directory in this path"
            )
        return self._get_first_wit_dir(os.path.dirname(path))

    def _get_real_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self.current_dir, path)

    def _get_wit_dir(self) -> str:
        return os.path.join(self.parent_wit_dir, '.wit')

    def _get_stage_dir(self) -> str:
        return os.path.join(self._get_wit_dir(), 'staging_area')

    def _get_images_dir(self) -> str:
        return os.path.join(self._get_wit_dir(), 'images')

    def get_active_branch(self) -> str:
        with open(self.activated_path, 'r') as file:
            return file.read()

    def get_all_branches(self) -> List[str]:
        with open(self.references_path, 'r') as file:
            text = file.read().splitlines()
        return [
            line.rpartition('=')[0]
            for line in text
        ]

    def get_commit_id(self, line: str = 'HEAD=') -> Optional[str]:
        """Return the last commit id done."""
        if not os.path.isfile(self.references_path):
            return None
        with open(self.references_path, 'r') as file:
            file_content = file.read().splitlines()
        line_num = -1
        for index, each_line in enumerate(file_content):
            if each_line.startswith(line):
                line_num = index
        if line_num == -1:  # In case there is no branch as expected
            return None
        head_line = file_content[line_num]
        parent_commit_id = head_line[len(line):]
        return parent_commit_id

    def get_parents_of_a_file(self, image_commit_id: str) -> List[str]:
        """Return the parent commit id of an image."""
        commit_id_path = os.path.join(
            self.images_dir, f'{image_commit_id}.txt'
        )
        with open(commit_id_path, 'r') as file:
            return file.read().splitlines()[0][len('parent='):].split(',')

    @staticmethod
    def get_path_files(directory: str) -> Iterator[str]:
        """Generates all the files paths in the given directory."""
        for dirpath, _, filesnames in os.walk(directory):
            for filename in filesnames:
                yield os.path.join(dirpath, filename)


class WitEditor(WitManager):
    def create_metadata_file(
        self, message: str, file_hash_name: str, branch_id: Optional[str]
    ) -> None:
        """Create the metadata file for the new backup."""
        new_file_path = os.path.join(self.images_dir, file_hash_name)
        with open(f'{new_file_path}.txt', 'w') as file:
            if branch_id is None:
                file.write(f'parent={self.get_commit_id()}\n')
            else:
                file.write(f'parent={self.get_commit_id()},{branch_id}\n')
            file.write(
                f'date={datetime.now().ctime()} {strftime("%z", gmtime())}\n'
                f'message={message}'
            )

    def update_references_file(
        self, commit_id: str, is_branch: bool = True
    ) -> None:
        """Create the references file."""
        if not os.path.isfile(self.references_path):
            with open(self.references_path, 'w') as file:
                file.write(
                    f'HEAD={commit_id}\n'
                    f'master={commit_id}\n'
                )
        else:
            with open(self.references_path, 'r') as file:
                text = file.read().splitlines()
            active_branch = self.get_active_branch()
            current_head_commit_id = self.get_commit_id()
            with open(self.references_path, 'w') as file:
                file.write(f'HEAD={commit_id}\n')
                for line in text[1:]:
                    if (
                        is_branch
                        and active_branch in line
                        and current_head_commit_id in line  # type: ignore
                    ):
                        file.write(f'{active_branch}={commit_id}\n')
                    else:
                        file.write(line + '\n')

    def remove_old_branch(self, branch_name: str) -> None:
        """Remove from the references text file a branch name, if exists."""
        with open(self.references_path, 'r') as file:
            text = file.read().splitlines()
        is_branch = self.get_commit_id(f'{branch_name}=')
        if is_branch is not None:
            with open(self.references_path, 'w') as file:
                for line in text:
                    if not line.startswith(branch_name):
                        file.write(line + '\n')

    def update_new_branch(self, branch_name: str) -> None:
        """Update the references text file according to the branch name."""
        current_head_commit_id = self.get_commit_id()
        self.remove_old_branch(branch_name)
        with open(self.references_path, 'a') as file:
            file.write(f'{branch_name}={current_head_commit_id}\n')

    def update_activated_branch(self, branch_name: str) -> None:
        """Update the activated text file to the new activated branch."""
        with open(self.activated_path, 'w') as file:
            file.write(branch_name)

    @staticmethod
    def copy_tree(
        src: str, dst: str, rel: str, ignore_files: Optional[List[str]] = None
    ) -> None:
        """Copy all the files in the real_path directory."""
        for dirpath, dirnames, filesnames in os.walk(src):
            rel_path = os.path.relpath(dirpath, rel)
            final_dir = os.path.join(dst, rel_path)

            for dirname in dirnames:
                final_dirname = os.path.join(final_dir, dirname)
                if not os.path.isdir(final_dirname):
                    os.mkdir(final_dirname)

            for filename in filesnames:
                file_rel_path = os.path.join(rel_path, filename)
                if not ignore_files or file_rel_path not in ignore_files:
                    src_filename = os.path.join(dirpath, filename)
                    shutil.copy2(src_filename, final_dir)

    def image_copy_files(self, commit_id_images_dir: str) -> None:
        """Copy the files to the image directory."""
        for directory in os.listdir(self.stage_dir):
            src_copy_dir = os.path.join(self.stage_dir, directory)
            dst_copy_dir = os.path.join(commit_id_images_dir, directory)
            if os.path.isdir(src_copy_dir):
                shutil.copytree(src_copy_dir, dst_copy_dir)
            else:
                shutil.copy2(src_copy_dir, dst_copy_dir)

    @staticmethod
    def create_dirs(
        final_dir: str, f: Callable[[str], None] = os.makedirs
    ) -> None:
        try:
            f(final_dir)
        except FileExistsError:
            _logger.warning(
                'The %s directory already exists', final_dir
            )


class WitStatus(WitManager):
    def __init__(self) -> None:
        super().__init__()
        self.last_commit_id = self.get_commit_id()
        if self.last_commit_id:
            self.commit_id_dir = os.path.join(
                self.images_dir, self.last_commit_id
            )
            self.stage_files = self._get_files(files=self.stage_dir)
            self.commit_id_files = self._get_files(files=self.commit_id_dir)
            self.original_files = self._get_files(files=self.real_path)

    def _get_files(self, files: str) -> List[str]:
        if files != self.real_path:
            length = len(files) + 1
        else:
            length = len(self.parent_wit_dir) + 1
        return [
            file[length:]
            for file in self.get_path_files(files)
        ]

    @staticmethod
    def compare_two_list_files(
        add_files_list: List[str], commit_on_files_list: List[str],
        add_files_dir: str, commit_on_files_dir: str
    ) -> Tuple[List[str], List[str]]:
        """Return the files that has changed and the not existing files."""
        untracked_files = []
        changed_files = []
        for file_path in add_files_list:
            if file_path not in commit_on_files_list:
                untracked_files.append(file_path)
            else:
                add_path = os.path.join(add_files_dir, file_path)
                commit_path = os.path.join(commit_on_files_dir, file_path)
                add_content, commit_content = WitStatus.compare_files_contents(
                    add_path, commit_path
                )
                hash_add_content = Hashing.by_content(add_content)
                hash_commit_content = Hashing.by_content(commit_content)
                if hash_add_content != hash_commit_content:
                    changed_files.append(file_path)
        return changed_files, untracked_files

    @staticmethod
    def compare_files_contents(
        add_path: str, commit_path: str
    ) -> Tuple[Text, Text]:
        """Return both files contents."""
        try:
            with open(add_path, 'r') as file_to_add:
                add_content = file_to_add.read()
            with open(commit_path, 'r') as commit_file:
                commit_content = commit_file.read()
        except UnicodeDecodeError:
            with open(add_path, 'br') as file_to_add:
                add_content = file_to_add.read()
            with open(commit_path, 'br') as commit_file:
                commit_content = commit_file.read()
        return add_content, commit_content

    @staticmethod
    def compare_changed_files_by_lines(
        files: Iterable[str], first_dir: str, second_dir: str,
        ancestor_dir: Optional[str] = None
    ) -> bool:
        """Compare whether the files can be merged."""
        for file in files:
            first_file = os.path.join(first_dir, file)
            second_file = os.path.join(second_dir, file)
            first_content, second_content = WitStatus.compare_files_contents(
                first_file, second_file
            )
            first_lines = first_content.splitlines()
            second_lines = second_content.splitlines()
            if ancestor_dir is not None:
                ancestor_file = os.path.join(ancestor_dir, file)
                ancestor_content, _ = WitStatus.compare_files_contents(
                    ancestor_file, first_file
                )
                ancestor_lines = ancestor_content.splitlines()

                for index, first_line in enumerate(first_lines):
                    second_line = second_lines[index]
                    ancestor_line = ancestor_lines[index]

                    if (
                        first_line != ancestor_line
                        and second_line != ancestor_line
                    ):
                        return False
            else:
                return first_content == second_content

        return True

    def check_all_changed_files(
        self, both_changed: Iterable[str], both_untracked: Iterable[str],
        branch_dir: str, ancestor_dir: str
    ) -> bool:
        are_changes_ok = self.compare_changed_files_by_lines(
            both_changed, branch_dir, self.commit_id_dir, ancestor_dir
        )
        are_untracked_ok = self.compare_changed_files_by_lines(
            both_untracked, branch_dir, self.commit_id_dir
        )
        return are_changes_ok and are_untracked_ok

    @staticmethod
    def file_after_merge(
        file: str, first_dir: str, second_dir: str, ancestor_dir: str
    ) -> str:
        """Return a changed file after merging contents."""
        first_file = os.path.join(first_dir, file)
        second_file = os.path.join(second_dir, file)
        ancestor_file = os.path.join(ancestor_dir, file)
        first_content, second_content = WitStatus.compare_files_contents(
            first_file, second_file
        )
        ancestor_content, _ = WitStatus.compare_files_contents(
            ancestor_file, first_file
        )
        first_lines = first_content.splitlines()
        second_lines = second_content.splitlines()
        ancestor_lines = ancestor_content.splitlines()

        new_file_str = ''
        index = 0
        for first_line in first_lines:
            second_line = second_lines[index]
            ancestor_line = ancestor_lines[index]
            if first_line != ancestor_line:
                new_file_str += f'{first_line}\n'
            else:
                new_file_str += f'{second_line}\n'
            index += 1
        new_file_str += '\n'.join(second_lines[index:])
        return new_file_str

    def get_changes_to_be_committed(self) -> List[str]:
        changed_since_last_commit, untracked_since_last_commit = (
            self.compare_two_list_files(
                self.stage_files, self.commit_id_files,
                self.stage_dir, self.commit_id_dir
            )
        )
        return changed_since_last_commit + untracked_since_last_commit

    def build_graph_tree(
        self, param: Optional[str], commit_id: Optional[str] = None,
        com_len: int = 12, include_branches: bool = True
    ) -> DefaultDict[str, List[str]]:
        if param:  # param == '--all'
            return self.build_all_graph_tree()
        graph_dict: DefaultDict[str, List[str]] = defaultdict(list)
        if commit_id is None:
            commit_id = self.last_commit_id
        commit_ids = [commit_id]

        branches = self.get_all_branches()
        return self.build_path_tree(
            commit_ids, com_len, include_branches, branches, graph_dict
        )

    def build_path_tree(
        self, commit_ids: List[Optional[str]], com_len: int,
        include_branches: bool, branches: List[str],
        graph_dict: DefaultDict[str, List[str]]
    ) -> DefaultDict[str, List[str]]:
        if (
            all(commit is None for commit in commit_ids)
            or all(commit == 'None' for commit in commit_ids)
        ):
            return graph_dict
        for commit in commit_ids:
            if commit is not None and commit != 'None':
                if include_branches:
                    for branch in branches:
                        if (
                            commit == self.get_commit_id(line=f'{branch}=')
                        ):
                            graph_dict[branch].append(commit[:com_len])
                parents_commit_ids = self.get_parents_of_a_file(commit)
                for parent in parents_commit_ids:
                    graph_dict[commit[:com_len]].append(parent[:com_len])
                graph_dict.update(self.build_path_tree(
                    parents_commit_ids, com_len, include_branches,
                    branches, graph_dict
                ))
                return graph_dict

    def build_all_graph_tree(
        self, com_len: int = 12, include_branches: bool = True
    ) -> DefaultDict[str, List[str]]:
        graph_dict = defaultdict(list)
        text_files = [
            text_file[:-len('.txt')]
            for text_file in fnmatch.filter(
                os.listdir(self.images_dir), '*.txt'
            )
        ]
        branches = self.get_all_branches()
        for commit_id in text_files:
            if include_branches:
                for branch in branches:
                    if (
                        commit_id == self.get_commit_id(line=f'{branch}=')
                    ):
                        graph_dict[branch].append(commit_id[:com_len])
            parents_commit_id = self.get_parents_of_a_file(commit_id)
            for parent in parents_commit_id:
                graph_dict[commit_id[:com_len]].append(parent[:com_len])
        return graph_dict

    @staticmethod
    def build_graph_items(
        items_list: List[Tuple[str, List[str]]]
    ) -> Iterator[Tuple[str, str]]:
        for key, values in items_list:
            for value in values:
                yield key, value

    def get_lowest_common_ancestor(
        self, branch_commit_id
    ) -> Optional[str]:
        head_tree = self.build_graph_tree(
            param=None, com_len=COMMIT_ID_LENGTH, include_branches=False
        )
        branch_tree = self.build_graph_tree(
            param=None, commit_id=branch_commit_id, com_len=COMMIT_ID_LENGTH,
            include_branches=False
        )
        ancestor = self.lowest_common_ancestor_dicts(head_tree, branch_tree)
        return ancestor

    def lowest_common_ancestor_dicts(
        self, first_dict_tree: DefaultDict[str, List[str]],
        second_dict_tree: DefaultDict[str, List[str]]
    ) -> Optional[str]:  # Dicts are ordered objects
        for item in first_dict_tree:
            if item in second_dict_tree:
                return item
