Gridster.js
===========

Gridster is a jQuery plugin that makes building intuitive draggable
layouts from elements spanning multiple columns. You can even
dynamically add and remove elements from the grid.

More at [http://gridster.net/](http://gridster.net/).

Public Service Announcement from Dustin Moore (dustmoo)
=======================================================

Gridster is not currently being actively maintained by 
[Ducksboard](http://ducksboard.com/).

I and others have been given access to the repo to help
 maintain and address issues.

I have created a fork of gridster that supports more advanced
 features, like widget-swapping and static widgets.

It can be found here: https://github.com/dustmoo/gridster.js

Currently the code-base is different and I don't have time to
reconcile the fork with this repo. 

If anyone would like to help me improve my fork and reconcile 
it with the main library I would be happy for the help.


License
=======

Distributed under the MIT license.

Whodunit
========

Gridster is built by [Ducksboard](http://ducksboard.com/).

dustmoo Modifications
===========

Changelog 2013-04-3

Fork now handles standard behavior properly with swap allowing larger widgets to shift down.

Changelog 2013-04-2

Added Demo to Repository.

Changelog 2013-02-27

Added "Static widget support" Static Items default to the "static" class.

You can customize this class by using the code below:

	$.gridster({
		static_class: 'custom_class',
		draggable: {
            items: ".gs_w:not(.custom_class)"
        }
	});

I have also added functions creating a much more thourough check of whether the player can occupy the space you are moving it too.
This version is much more reliable in swapping space with widgets.

There are also new options for Maximum Rows and Maximum Columns:
	
	$.gridster({
		max_rows: map_rows,
    	max_cols: map_cols,
    	shift_larger_widgets_down: false
    });

Setting the maximum amount of rows only completely works if you disable shifting larger widgets down at the moment. 


Changelog 2012-11-26

Reworked swapping functionality to better handle large to small widget handling.

---

Widgets of smaller or equal size to the dragged widget (player) 
will swap places with the original widget. 

This causes tiles to swap left and right as well as up and down.

By default smaller players will shift larger widgets down.

I have added an option to prevent this behavior:

	$.gridster({
		shift_larger_widgets_down: false
	});

By setting shift_larger_widgets_down to false, smaller widgets will not displace larger ones.



