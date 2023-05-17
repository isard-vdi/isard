/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var DEBUG = false;
function processError(response,form){
    if (response.status === 0){
        alert('Lost connection. Check your network.')
    }else if (response.status === 409){
        form.find("#name").addClass('js_error');
        form.find("#name").parsley().removeError('myError');
        form.find("#name").parsley().addError('myError', {message: jQuery.parseJSON(response.responseText).description});
    }else{
        alert(jQuery.parseJSON(response.responseText).description)
    }
    if( DEBUG ) alert(JSON.stringify(jQuery.parseJSON(response.responseText), null, 4))
}

function removeError(form){
    form.find("#name").parsley().removeError('myError');
}
/**
 * Resize function without multiple trigger
 *
 * Usage:
 * $(window).smartresize(function(){
 *     // code here
 * });
 */
(function($,sr){
    // debouncing function from John Hann
    // http://unscriptable.com/index.php/2009/03/20/debouncing-javascript-methods/
    var debounce = function (func, threshold, execAsap) {
      var timeout;

        return function debounced () {
            var obj = this, args = arguments;
            function delayed () {
                if (!execAsap)
                    func.apply(obj, args);
                timeout = null;
            }

            if (timeout)
                clearTimeout(timeout);
            else if (execAsap)
                func.apply(obj, args);

            timeout = setTimeout(delayed, threshold || 100);
        };
    };

    // smartresize
    jQuery.fn[sr] = function(fn){  return fn ? this.bind('resize', debounce(fn)) : this.trigger(sr); };

})(jQuery,'smartresize');
/**
 * To change this license header, choose License Headers in Project Properties.
 * To change this template file, choose Tools | Templates
 * and open the template in the editor.
 */

// Validator.js
      // initialize the validator function
      validator.message.date = 'not a real date';

      // validate a field on "blur" event, a 'select' on 'change' event & a '.reuired' classed multifield on 'keyup':
      $('form')
        .on('blur', 'input[required], input.optional, select.required', validator.checkField)
        .on('change', 'select.required', validator.checkField)
        .on('keypress', 'input[required][pattern]', validator.keypress);
        //~ .on('keypress', 'input[required][pattern]', function(){console.log('press')});

      $('.multi.required').on('keyup blur', 'input', function() {
        validator.checkField.apply($(this).siblings().last()[0]);
      });

      $('form').submit(function(e) {
        e.preventDefault();
        var submit = true;

        // evaluate the form using generic validaing
        if (!validator.checkAll($(this))) {
          submit = false;
        }

        if (submit)
          this.submit();

        return false;
        });
// /Validator.js

//PNotify
        var stack_center = {"dir1": "down", "dir2": "right", "firstpos1": 25, "firstpos2": ($(window).width() / 2) - (Number(PNotify.prototype.options.width.replace(/\D/g, '')) / 2)};
                $(window).resize(function(){
                    stack_center.firstpos2 = ($(window).width() / 2) - (Number(PNotify.prototype.options.width.replace(/\D/g, '')) / 2);
                });
    PNotify.prototype.options.styling = "bootstrap3";
// /PNotify

// Sidebar
var CURRENT_URL = window.location.href.split('#')[0].split('?')[0],
    $BODY = $('body'),
    $MENU_TOGGLE = $('#menu_toggle'),
    $SIDEBAR_MENU = $('#sidebar-menu'),
    $SIDEBAR_FOOTER = $('.sidebar-footer'),
    $LEFT_COL = $('.left_col'),
    $RIGHT_COL = $('.right_col'),
    $NAV_MENU = $('.nav_menu'),
    $FOOTER = $('footer');

function notify(data) {
  new PNotify({
    title: data.title,
    text: data.text,
    hide: true,
    delay: 3000,
    icon: data.icon,
    opacity: 1,
    type: data.type
  })
}


function init_sidebar() {
// TODO: This is some kind of easy fix, maybe we can improve this
var setContentHeight = function () {
    // reset height
    $RIGHT_COL.css('min-height', $(window).height());

    var bodyHeight = $BODY.outerHeight(),
        footerHeight = $BODY.hasClass('footer_fixed') ? -10 : $FOOTER.height(),
        leftColHeight = $LEFT_COL.eq(1).height() + $SIDEBAR_FOOTER.height(),
        contentHeight = bodyHeight < leftColHeight ? leftColHeight : bodyHeight;

    // normalize content
    contentHeight -= $NAV_MENU.height() + footerHeight;

    $RIGHT_COL.css('min-height', contentHeight);
};

  $SIDEBAR_MENU.find('a').on('click', function(ev) {
        var $li = $(this).parent();

        if ($li.is('.active')) {
            $li.removeClass('active active-sm');
            $('ul:first', $li).slideUp(function() {
                setContentHeight();
            });
        } else {
            // prevent closing menu if we are on child menu
            if (!$li.parent().is('.child_menu')) {
                $SIDEBAR_MENU.find('li').removeClass('active active-sm');
                $SIDEBAR_MENU.find('li ul').slideUp();
            }else
            {
                if ( $BODY.is( ".nav-sm" ) )
                {
                    $SIDEBAR_MENU.find( "li" ).removeClass( "active active-sm" );
                    $SIDEBAR_MENU.find( "li ul" ).slideUp();
                }
            }
            $li.addClass('active');

            $('ul:first', $li).slideDown(function() {
                setContentHeight();
            });
        }
    });

// toggle small or large menu
$MENU_TOGGLE.on('click', function() {
        if ($BODY.hasClass('nav-md')) {
            $SIDEBAR_MENU.find('li.active ul').hide();
            $SIDEBAR_MENU.find('li.active').addClass('active-sm').removeClass('active');
        } else {
            $SIDEBAR_MENU.find('li.active-sm ul').show();
            $SIDEBAR_MENU.find('li.active-sm').addClass('active').removeClass('active-sm');
        }

    $BODY.toggleClass('nav-md nav-sm');

    setContentHeight();
});

    // check active menu
    $SIDEBAR_MENU.find('a[href="' + CURRENT_URL + '"]').parent('li').addClass('current-page');

    $SIDEBAR_MENU.find('a').filter(function () {
        return this.href == CURRENT_URL;
    }).parent('li').addClass('current-page').parents('ul').slideDown(function() {
        setContentHeight();
    }).parent().addClass('active');

    // recompute content when resizing
    $(window).smartresize(function(){
        setContentHeight();
    });

    setContentHeight();

    // fixed sidebar
    if ($.fn.mCustomScrollbar) {
        $('.menu_fixed').mCustomScrollbar({
            autoHideScrollbar: true,
            theme: 'minimal',
            mouseWheel:{ preventDefault: true }
        });
    }
};
// /Sidebar

$(document).ready(function() {
    init_sidebar();
    $('input').iCheck({
        checkboxClass: 'icheckbox_flat-green',
        radioClass: 'iradio_flat-green',
    })
});

JSON.unflatten = function(data) {
    "use strict";
    if (Object(data) !== data || Array.isArray(data))
        return data;
    var regex = /\-?([^-\[\]]+)|\[(\d+)\]/g,
        resultholder = {};
    for (var p in data) {
        var cur = resultholder,
            prop = "",
            m;
        while (m = regex.exec(p)) {
            cur = cur[prop] || (cur[prop] = (m[2] ? [] : {}));
            prop = m[2] || m[1];
        }
        cur[prop] = data[p];
    }
    return resultholder[""] || resultholder;
};

// Form serialization

        (function($){
            $.fn.serializeObject = function(){
                var self = this,
                    json = {},
                    push_counters = {},
                    patterns = {
                          "validate": /^[a-z][a-z0-9_-]*(?:\[(?:\d*|[a-z0-9_-]+)\])*$/i,
                          "key":      /[a-z0-9_-]+|(?=\[\])/gi,
                          "named":    /^[a-z0-9_-]+$/i,
                        //~ "validate": /^[a-zA-Z][a-zA-Z0-9_]*(?:\[(?:\d*|[a-zA-Z0-9_]+)\])*$/,
                        //~ "key":      /[a-zA-Z0-9_]+|(?=\[\])/g,
                        "push":     /^$/,
                        "fixed":    /^\d+$/,
                        //~ "named":    /^[a-zA-Z0-9_]+$/
                    };


                this.build = function(base, key, value){
                    base[key] = value;
                    return base;
                };

                this.push_counter = function(key){
                    if(push_counters[key] === undefined){
                        push_counters[key] = 0;
                    }
                    return push_counters[key]++;
                };

                $.each($(this).serializeArray(), function(){

                    // skip invalid keys
                    if(!patterns.validate.test(this.name)){
                        return;
                    }

                    var k,
                        keys = this.name.match(patterns.key),
                        merge = this.value,
                        reverse_key = this.name;

                    while((k = keys.pop()) !== undefined){

                        // adjust reverse_key
                        reverse_key = reverse_key.replace(new RegExp("\\[" + k + "\\]$"), '');

                        // push
                        if(k.match(patterns.push)){
                            merge = self.build([], self.push_counter(reverse_key), merge);
                        }

                        // fixed
                        else if(k.match(patterns.fixed)){
                            merge = self.build([], k, merge);
                        }

                        // named
                        else if(k.match(patterns.named)){
                            merge = self.build({}, k, merge);
                        }
                    }

                    json = $.extend(true, json, merge);
                });

                return json;
            };
        })(jQuery);


function dtUpdateInsertoLD(table, data, append){
    //Quickly appends new data rows.  Does not update rows
    if(append == true){
        table.rows.add(data);

    //Locate and update rows by rowId or add if new
    }else{

            found=false;
            table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
                if(this.data().id==data.id){
                    table.row(rowIdx).data(data).invalidate();
                    found=true;
                    return false; //Break
                }
            });
            if(!found){
                table.row.add(data);
                }
    }

    //Redraw table maintaining paging
    table.draw(false);
}

function dtUpdateInsert(table, data, append){
    //Quickly appends new data rows.  Does not update rows
    new_id=false
    if(append == true){
        table.rows.add(data);
        new_id=true
    //Locate and update rows by rowId or add if new
    }else{
        if(typeof(table.row('#'+data.id).id())=='undefined'){
            // Does not exists yet
            table.row.add(data);
            new_id=true
        }else{
            // Exists, do update
            data={...table.row("#"+data.id).data(),...data}
            table.row('#'+data.id).data(data).invalidate();
        }
    }

    //Redraw table maintaining paging
    table.draw(false);
    return new_id
}

function dtUpdateOnly(table, data){
        if(typeof(table.row('#'+data.id).id())=='undefined'){
            // Does not exists yes
        }else{
            // Exists, do update
            table.row('#'+data.id).data(data).invalidate();
        }
    //Redraw table maintaining paging
    table.draw(false);
}

function toggleRow(table_row, e) {
    if (['','sorting_1','form-check-input'].includes(e.target.className)) {
        $(table_row).toggleClass('active');
        if ($(table_row).hasClass('active')) {
            $(table_row).find('input').prop('checked', true);
        } else {
            $(table_row).find('input').prop('checked', false);
        }
    }
}

function infoDomains(value, tbody) {
    var html = `<tr><th>${value['kind']}</th>`
    if (value['user_name']) {
        html += `<th>${value['user_name']}</th>`
    } else {
        html += `<th>-</th>`
    }
    html += `<th>${value['name']}</th>
    </tr>`
    return tbody.append(html);
}

function disableFirstOption (id) {
  $(id + ' select').prepend(
    $('<option></option>').attr('value', null).text('  -- ')
  )
}

function showAndHideByCheckbox (checkboxSelector, divSelector) {
  divSelector.hide()
  checkboxSelector.on('ifChecked', function (event) {
    divSelector.show()
  })
  checkboxSelector.on('ifUnchecked', function (event) {
    divSelector.hide()
  })
}


// Panel toolbox
$(document).ready(function() {
    $('.collapse-link').on('click', function() {
        var $BOX_PANEL = $(this).closest('.x_panel'),
            $ICON = $(this).find('i'),
            $BOX_CONTENT = $BOX_PANEL.find('.x_content');

        // fix for some div with hardcoded fix class
        if ($BOX_PANEL.attr('style')) {
            $BOX_CONTENT.slideToggle(200, function(){
                $BOX_PANEL.removeAttr('style');
            });
        } else {
            $BOX_CONTENT.slideToggle(200);
            $BOX_PANEL.css('height', 'auto');
        }

        $ICON.toggleClass('fa-chevron-up fa-chevron-down');
    });

    $('.close-link').click(function () {
        var $BOX_PANEL = $(this).closest('.x_panel');

        $BOX_PANEL.remove();
    });
});

function show_no_os_hardware_template_selected() {
  $('#modal_add_install').closest('.x_panel').addClass('datatables-error');
  $('#datatables-install-error-status').html('No OS hardware template selected').addClass('my-error');
}

function getOS() {
    var userAgent = window.navigator.userAgent,
        platform = window.navigator.platform,
        macosPlatforms = ['Macintosh', 'MacIntel', 'MacPPC', 'Mac68K'],
        windowsPlatforms = ['Win32', 'Win64', 'Windows', 'WinCE'],
        iosPlatforms = ['iPhone', 'iPad', 'iPod'],
        os = null;
    if (macosPlatforms.indexOf(platform) !== -1) {
      os = 'MacOS';
    } else if (iosPlatforms.indexOf(platform) !== -1) {
      os = 'iOS';
    } else if (windowsPlatforms.indexOf(platform) !== -1) {
      os = 'Windows';
    } else if (/Android/.test(userAgent)) {
      os = 'Android';
    } else if (!os && /Linux/.test(platform)) {
      os = 'Linux';
    }
    return os;
}

// Id must always be the last column
function adminShowIdCol (datatable, table_id) {
    if ($('meta[id=user_data]').attr('data-role') == 'admin'){
        document.addEventListener('keydown', KeyPress)
        function KeyPress(e) {
            var evtobj = window.event? event : e
            if (evtobj.keyCode == 73 && evtobj.ctrlKey && evtobj.altKey) {
                // Get the column API object
                var column = datatable.column(datatable.columns().header().length-1);
                // Toggle the visibility
                column.visible(!column.visible());
            }
      }
    }
}

function waitDefined (name, callback) {
    var interval = setInterval(function () {
        if (!window.hasOwnProperty(name)) return
        clearInterval(interval)
        callback()
    }, 100)
}

function getUrlParam(paramName){
    let searchParam = window.location.href.slice(window.location.href.indexOf('?') + 1).split(paramName + "=")
    if (searchParam.length > 1) {
        return searchParam[1].replaceAll("%20", " ");;
    }
}

function formatTimestampUTC(timestamp) {
    // Supported formats: ISO 8601 and Unix Timestamp
    // If using Unix format, the "timestamp" variable must be entered multiplied by 1000
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = ('0' + (date.getMonth() + 1)).slice(-2);
    const day = ('0' + date.getDate()).slice(-2);
    const hour = ('0' + date.getHours()).slice(-2);
    const minute = ('0' + date.getMinutes()).slice(-2);
    const second = ('0' + date.getSeconds()).slice(-2);
    const formattedDate = `${year}-${month}-${day} ${hour}:${minute}:${second}`;

    return formattedDate;
}