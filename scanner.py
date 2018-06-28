# This script assumes a well formed kernel.txt and the descriptions.txt exist in the same directory.
# It will annotate the kernel options and create a new kernel.csv file which can be imported in Excel
import os
from constants import *


def get_key(line):
    line = line[line.find('CONFIG_'):]
    line = line.split()[0]
    line = line.split('=')[0]
    return line.strip()


def get_value(line):
    return line.split('=')[1].split('\t')[0].strip()


def get_description(line):
    """
    Fetches the description from a line, assuming tabs, option assignment or whitespace as a delimiter
    :param line:
    :return:
    """
    result = line.strip().split('\t')
    # Well formed case, should have 2 elements
    # Otherwise, the delimiter might be whitespace. Then separate by =
    if len(result) != 2:
        result = line.strip().split('=y')
    if len(result) != 2:
        result = line.strip().split('=m')
    # String case
    if len(result) != 2 and line.find('="') != -1:
        line = line[line.find('="') + 2:]
        return line[line.find('"') + 1:].strip()
    # Number case
    if len(result) != 2:
        line = line[line.find('=') + 1:]
        for letter in line:
            if str(letter).isspace():
                return line[line.find(letter):].strip()
    return result[1].strip() if len(result) == 2 else ""


def load_descriptions():
    """
    Loads all descriptions from the descriptions.txt file, indicating fields which have no description
    :return: Dict of all keys and descriptions
    """
    with open(descriptions_file, 'r') as file:
        result = {}
        no_description = 0
        with_description = 0
        for line in file.readlines():
            if line.startswith('CONFIG_'):
                key = get_key(line)
                description = get_description(line)
                result[key] = description
                if description.strip() in ['', ' ', '\n']:
                    no_description = no_description + 1
                    # print(f"No description found for {key}")
                else:
                    with_description = with_description + 1
        # print(f"Total keys without descriptions: {no_description}\nTotal keys with description: {with_description}")
        return result


def print_descriptions():
    descriptions = load_descriptions()
    for description in descriptions:
        print(description + " " + descriptions[description] + '\n')


def process_line(line, descriptions):
    key = get_key(line)[7:]
    value = 'n' if line.startswith('#') else get_value(line)
    param_type = descriptions[key][1] if key in descriptions else ''
    name = descriptions[key][2] if key in descriptions else ''
    default = descriptions[key][3] if key in descriptions else ''
    dependency = descriptions[key][4] if key in descriptions else ''
    description = descriptions[key][5] if key in descriptions else ''
    return '\t'.join([key.strip(), value.strip(), param_type.strip(), name.strip(), default.strip(), dependency.strip(),
                      description.strip()])


def annotate_kernel_file_csv():
    with open(kernel_config, 'r') as file:
        with open('kernel.csv', 'w') as ofile:
            descriptions = merge_descriptions()
            for line in [line.strip() for line in file.readlines()]:
                if line.startswith('CONFIG') or line.startswith('# CONFIG'):
                    ofile.write(process_line(line, descriptions) + '\n')
                else:
                    ofile.write(line + '\n')


def find_dependency_start(word):
    for c in word:
        if c.isupper() or c.isdigit() or c in '!(':
            return word.find(c)
    return -1


def find_dependency_end(text):
    # Ignore any depends on
    temp_text = text.replace('depends on', 'Ü')
    diff = len(text) - len(temp_text)
    for c in temp_text:
        # Exceptions for dependencies set to a certain tristate
        if c in 'ynm':
            continue
        if c.islower() or c == '-':
            return temp_text.find(c) + diff
    # In case of no findings yet, the whole string is a dependency
    return len(text)


def remove_internal_whitespace(word):
    new_word = ""
    while new_word != word:
        word = word.replace('  ', ' ').replace('\t', ' ').replace('\n', ' ')
        new_word = word.replace('  ', ' ').replace('\t', ' ').replace('\n', ' ')
    return word


def parse_key(line):
    if line.startswith('config'):
        return line[line.find('config ') + 7:].strip()


def parse_default(line, param_type):
    line = line.strip()
    if line.startswith('default '):
        line = line[8:]
        # Sort out false positives. To know what we expect, we need the type
        if param_type in bool_types:
            for c in line:
                if c.islower() and c not in 'ymnif':
                    return
        elif param_type == 'int':
            for c in line:
                if c.islower() and c not in 'if' or c.isdigit():
                    return
        elif param_type == 'hex':
            for c in line:
                if c.islower() and c is not 'x' or c.isupper() and c not in 'ABCDEF':
                    return
        return line.strip()


def find_name(content, delimiter):
    # Name is before default and before depends and before help
    next_field = content.find('default')
    if next_field == -1:
        next_field = content.find('depends')
        if next_field == -1:
            next_field = content.find('help')

    first_paren = content.find(delimiter) + 1

    # If there are no parentheses at all, there is no name
    # If first parenthesis comes after the next, it belongs to a different field and there is no name
    # If there is no next field, the first parens belong to name
    if first_paren != 0 and (next_field == -1 or first_paren < next_field):
        second_paren = content[first_paren:].find(delimiter)
        return content[first_paren: first_paren + second_paren]
    else:
        return ""


def parse_param_type_and_name(line):
    words = line.split()
    # Exit if the line is not indicating a type
    if not words or words[0] not in types:
        return
    # The rest of the line is the name OR in some cases the default
    name_is_default = False
    rest = ''
    # If there is just one element in words, there is no name
    if len(words) >= 2:
        rest = ' '.join(words[1:])
        if rest[0] in 'ynm' and (len(rest) == 1 or rest[1] == ' '):
            name_is_default = True
    return words[0], rest, name_is_default


def remove_comments(lines):
    lines_to_remove = []
    for line in lines:
        if line.strip().startswith('#'):
            lines_to_remove.append(line)
    for line_to_remove in lines_to_remove:
        lines.remove(line_to_remove)
    return lines


def parse_dependency(content):
    # Single line dependency parsing
    content = content.strip()
    if content.startswith('depends on '):
        return content[11:]

        # Assumes hard to parse multiline dependencies with and without new depends on keywords
        # dependencies_index = content.find('depends on ')
        # if dependencies_index != -1:
        #    dependency_start_index = find_dependency_start(content[dependencies_index:]) + dependencies_index
        #    dependency_end_index = find_dependency_end(content[dependency_start_index:]) + dependency_start_index
        #    # Remove multiple depends on strings
        #    result = content[dependency_start_index: dependency_end_index]
        #    result = ', '.join([dependency.strip() for dependency in result.split('depends on ')])
        #    return result
        # else:
        #    return ''


def parse_file(filename):
    with open(filename, 'r') as file:

        lines = file.readlines()
        lines = remove_comments(lines)

        content = ''.join(lines)

        print(content)
        # Set default values
        strings = content.split()
        key = strings[1]
        param_type = ""
        default = []
        name = ""
        dependency = []
        description = ""

        # Line-based parsing
        for line in lines:
            if parse_key(line):
                key = parse_key(line)
            if parse_param_type_and_name(line):
                param_type, rest, is_default = parse_param_type_and_name(line)
                if is_default:
                    default.append(rest)
                else:
                    name = rest
            if parse_dependency(line):
                dependency.append(parse_dependency(line))

        for line in lines:
            if parse_default(line, param_type):
                default.append(parse_default(line, param_type))
        default = ','.join(default)
        dependency = ','.join(dependency)

        # Content-based parsing
        if len(lines) >= 2:
            # Find help
            help_line_index = content.find('help')
            # Find newline
            help_text_with_caption = content[help_line_index:]
            first_newline_index = help_text_with_caption.find('\n')
            description = help_text_with_caption[first_newline_index:].strip()
            # Inline description
            description = remove_internal_whitespace(description.replace('\n', '').replace('\t', ''))
        # print(f'\nKey: {key}\nParameter value: {param_type}\nName: {name}\nDefault: {default}\nDependency: {dependency}\nDescription: {description}\n')
        return key, param_type, name, default, dependency, description


def parse_files():
    modules_path = os.listdir(path)
    modules = {}
    for filename in modules_path:
        modules[filename] = parse_file(path + '\\' + filename)
    return modules


def merge_descriptions():
    descriptions = load_descriptions()
    mods = parse_files()

    descriptions_keys = [key[7:] for key in descriptions.keys()]
    mods_keys = [key for key in mods.keys()]
    combined_keys = set(descriptions_keys).union(mods_keys)

    result = {}

    for key in combined_keys:
        # 1. Get module description
        if key in mods_keys:
            module_tuple = mods[key]
            # Also add the others
            if module_tuple[5] == "" and module_tuple[0] in descriptions_keys:
                result[key] = ([module_tuple[0], module_tuple[1], module_tuple[2], module_tuple[3], module_tuple[4],
                                descriptions['CONFIG_' + module_tuple[0]]])
            else:
                result[key] = module_tuple
        else:
            # 2. Description will be based only in internal description
            result[key] = (key, "", "", "", "", descriptions['CONFIG_' + key])
    return result


for i in (parse_file(path + '\\' + 'CRYPTO_AES_MIN_KEYLEN')):  # RCU_FAST_NO_HZ
    print(i)
    # print(parse_file(path + '\\' + 'HAVE_UNSTABLE_SCHED_CLOCK'))
    # print(parse_file(path + '\\' + 'ARCH_DEFCONFIG'))
    # print(parse_file(path + '\\' + 'ARCH_HWEIGHT_CFLAGS'))
    # print(parse_file(path + '\\' + 'AUDIT_ARCH'))
    # print(parse_file(path + '\\' + 'HAVE_ARCH_TRANSPARENT_HUGEPAGE'))
    # print(parse_file(path + '\\' + 'CRYPTO_AES_MIN_KEYLEN'))
    # print(parse_file(path + '\\' + 'CRYPTO_MANAGER2'))
    # print(parse_file(path + '\\' + 'INTEL_IDLE'))

    # annotate_kernel_file_csv()

