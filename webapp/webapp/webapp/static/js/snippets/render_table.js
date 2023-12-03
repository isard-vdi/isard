//   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
//
//   This file is part of IsardVDI.
//
//   IsardVDI is free software: you can redistribute it and/or modify
//   it under the terms of the GNU Affero General Public License as published by
//   the Free Software Foundation, either version 3 of the License, or (at your
//   option) any later version.
//
//   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
//   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
//   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
//   details.
//
//   You should have received a copy of the GNU Affero General Public License
//   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
//
// SPDX-License-Identifier: AGPL-3.0-or-later

function renderTable(data, parentElement, level, renderCallback) {
    level = level || 1;
    $.each(data, function(index, item) {
      const row = $('<tr>').addClass('nested-level-' + level);
      if (renderCallback) {
        renderCallback(row, item, level);
      }
      parentElement.append(row);
      if (item.children && item.children.length > 0) {
        renderTable(item.children, parentElement, level + 1, renderCallback); // Recursively render children
      }
    });
return parentElement;
}

// Custom rendering callback function for table rows
function renderTemplateTree(row, item, level) {
    // Title column (indented based on level)
    row.append('<td class="nested-td nested-level-' + level + '">' + '&nbsp;&nbsp;'.repeat(level - 1) + '<i class="fa ' + (item.kind === 'template' ? 'fa-cube' : 'fa-desktop') + '"></i>&nbsp;' + item.title + '</td>');
    // Template/Desktop column
    row.append('<td class="nested-td">' + (item.kind === 'template' ? 'Template' : 'Desktop') + '</td>');
    // Duplicate column
    row.append('<td class="nested-td">' + (item.duplicate_parent_template ? '<i class="fa fa-check"></i>' : '') + '</td>');
    // User column
    row.append('<td class="nested-td">' + item.user + '</td>');
    // Category column
    row.append('<td class="nested-td">' + item.category + '</td>');
    // Group column
    row.append('<td class="nested-td">' + item.group + '</td>');
}

// Custom rendering callback function for table rows
function renderDesktopTree(row, item, level) {
  count= item.parents_count+1
  row.append('<td class="nested-td">' + count + '</td>');
  // Title column (indented based on level)
  row.append('<td class="nested-td><i class="fa fa-cube"></i>&nbsp;' + item.name + '</td>');
  // User column
  row.append('<td class="nested-td">' + item.username + '</td>');
  // Category column
  row.append('<td class="nested-td">' + item.category_name + '</td>');
  // Group column
  row.append('<td class="nested-td">' + item.group_name + '</td>');
}