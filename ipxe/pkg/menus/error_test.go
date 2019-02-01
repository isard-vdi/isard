/*
 * Copyright (C) 2019 Néfix Estrada <nefixestrada@gmail.com>
 * Author: Néfix Estrada <nefixestrada@gmail.com>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

package menus_test

import (
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/menus"
)

func TestGenerateError(t *testing.T) {
	expected := `#!ipxe
echo There was an error during tests. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`

	menu, err := menus.GenerateError("during tests")
	if err != nil {
		t.Errorf("unexpected error %v", err)
	}

	if menu != expected {
		t.Errorf("expecting %s, but got %s", expected, menu)
	}
}
