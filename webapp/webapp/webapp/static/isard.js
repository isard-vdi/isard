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

    $SIDEBAR_MENU.find('.current-page ul').show();

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
    });

    // Read file content on change and store in the companion hidden input
    $(document).on('change', 'input[type="file"][data-file-content]', function () {
        var $hidden = $(this).siblings('input[type="hidden"]');
        var file = this.files[0];
        if (file) {
            var accept = $(this).attr('accept');
            if (accept && accept.indexOf(file.type) === -1) {
                new PNotify({
                    text: 'File type ' + file.type + ' not allowed.',
                    type: 'error',
                    delay: 3000
                });
                $(this).val('');
                $hidden.val('').trigger('change');
                return;
            }
            var reader = new FileReader();
            reader.onload = function (e) {
                $hidden.val(e.target.result).trigger('change');
            };
            if (file.type.startsWith('image/')) {
                reader.readAsDataURL(file);
            } else {
                reader.readAsText(file);
            }
        } else {
            $hidden.val('').trigger('change');
        }
    });

    // Toggle download link and preview when companion hidden input changes
    $(document).on('change', 'input[type="hidden"][data-file-content]', function () {
        var val = $(this).val();
        $(this).siblings('.file-content-download').toggle(!!val);
        var $preview = $(this).siblings('.file-content-preview');
        if ($preview.length) {
            if (val && val.indexOf('data:') === 0) {
                $preview.html('<img src="' + val + '" />').show();
            } else {
                $preview.empty().hide();
            }
        }
    });

    // Download file content from companion hidden input on click
    $(document).on('click', '.file-content-download', function () {
        var content = $(this).siblings('input[type="hidden"]').val();
        if (!content) return false;
        var blob = new Blob([content], { type: 'application/octet-stream' });
        var url = URL.createObjectURL(blob);
        $(this).attr('href', url);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    });
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
    var html = `<tr><td>${value['kind']}</td>`
    if (value['user_name']) {
        html += `<td>${value['user_name']}</td>`
    } else {
        html += `<td>-</td>`
    }
    html += `<td>${value['name']}</td> 
                ${value["kind"] == "desktop" ? "<td>" + value["category"] + "</td>" : ""}
            </tr>`
    return tbody.append(html);
}

function disableFirstOption (id) {
  $(id + ' select').prepend(
    $('<option selected></option>').attr('value', null).text('  -- ')
  )
}

/**
 * Toggles the visibility of a form section and updates Parsley validation exclusion.
 * When disabled, the section is hidden and its inputs are excluded from validation.
 * When enabled, the section is shown and its inputs are included in validation.
 *
 * @param {jQuery} $container - The form section container to toggle.
 * @param {boolean} enabled - Whether the section should be visible and validated.
 */
function toggleFormSection ($container, enabled) {
  $container.toggle(enabled);
  $container.find(':input').attr('data-parsley-excluded', !enabled);
  $container.find(':checkbox').trigger('ifChanged');
  var $form = $container.closest('form');
  if ($form.length) {
    var activeElement = document.activeElement;
    $form.parsley().validate();
    if (activeElement && document.activeElement !== activeElement) {
      activeElement.focus();
    }
  }
}

/**
 * Sets up conditional visibility and required state for provider config fields.
 *
 * @param {jQuery} $container - Container element holding the config fields.
 * @param {string} namePrefix - Bracket-notation prefix for field names.
 * @param {Object} config - Configuration object with:
 * @param {Array}  [config.fieldsWithRegex] - Field names that have a regex counterpart
 *        (derived by replacing 'field' with 'regex' in the name).
 * @param {Object} [config.fieldVisibility] - Map of field names to visibility conditions
 *        (checkbox, optional empty field).
 * @param {Array}  [config.mutualRequired] - Pairs of field names where at least one is required
 *        (e.g. [['metadata_url', 'metadata_file']]).
 * @param {Object} [config.externalRequired] - Map of field names to external jQuery checkbox
 *        elements that control whether the field is required.
 */
function setupProviderFieldDependencies ($container, namePrefix, config) {
  var fieldsWithRegex = config.fieldsWithRegex || [];
  var fieldVisibility = config.fieldVisibility || {};
  var mutualRequired = config.mutualRequired || [];
  var externalRequired = config.externalRequired || {};

  function setRequired ($field, required) {
    var parsleyField = $field.parsley();
    if (required) {
      $field.attr('required', 'required');
      if (parsleyField) parsleyField.validate();
    } else {
      $field.removeAttr('required');
      if (parsleyField) parsleyField.reset();
    }
    $field.closest('.item.form-group').find('.required').toggle(required);
  }

  function getField (name) {
    return $container.find("[name='" + namePrefix + "[" + name + "]']");
  }

  function getFieldSection (name) {
    return getField(name).closest('.item.form-group');
  }

  function updateRegexVisibility (fieldName) {
    var regexName = fieldName.replace('field', 'regex');
    var fieldVisible = getField(fieldName).attr('data-parsley-excluded') !== 'true';
    var hasField = fieldVisible && !!getField(fieldName).val();
    toggleFormSection(getFieldSection(regexName), hasField);
    setRequired(getField(regexName), hasField);
  }

  function updateFieldVisibility (fieldName) {
    var condition = fieldVisibility[fieldName];
    if (!condition) return;
    var visible = getField(condition.checkbox).is(':checked');
    if (condition.empty) {
      visible = visible && !getField(condition.empty).val();
    }
    toggleFormSection(getFieldSection(fieldName), visible);
    setRequired(getField(fieldName), visible && !condition.optional);
    if (fieldsWithRegex.indexOf(fieldName) !== -1) {
      updateRegexVisibility(fieldName);
    }
  }

  function updateExternalRequired (fieldName) {
    var $checkbox = externalRequired[fieldName];
    var $field = getField(fieldName);
    var required = $checkbox.is(':checked');
    setRequired($field, required);
    $field.attr('data-parsley-excluded', !required && !$field.val());
    if (fieldsWithRegex.indexOf(fieldName) !== -1) {
      updateRegexVisibility(fieldName);
    }
  }

  function updateMutualRequired (pair) {
    var $a = getField(pair[0]);
    var $b = getField(pair[1]);
    var aVal = $a.val();
    var bVal = $b.val();
    setRequired($a, !bVal);
    setRequired($b, !aVal);
  }

  // Mutual required pairs
  $.each(mutualRequired, function (_, pair) {
    getField(pair[0]).off('input.prov-req').on('input.prov-req', function () {
      updateMutualRequired(pair);
    });
    getField(pair[1]).off('input.prov-req').on('input.prov-req', function () {
      updateMutualRequired(pair);
    });
  });

  // field -> regex visibility
  $.each(fieldsWithRegex, function (_, fieldName) {
    getField(fieldName).off('input.prov-req').on('input.prov-req', function () {
      updateRegexVisibility(fieldName);
    });
  });

  // field visibility conditions
  var checkboxTriggers = {};
  var inputTriggers = {};
  $.each(fieldVisibility, function (fieldName, condition) {
    var cb = condition.checkbox;
    if (!checkboxTriggers[cb]) checkboxTriggers[cb] = [];
    checkboxTriggers[cb].push(fieldName);
    if (condition.empty) {
      var emp = condition.empty;
      if (!inputTriggers[emp]) inputTriggers[emp] = [];
      inputTriggers[emp].push(fieldName);
    }
  });
  $.each(checkboxTriggers, function (trigger, fields) {
    getField(trigger).off('ifChecked.prov-req ifUnchecked.prov-req ifChanged.prov-req')
      .on('ifChecked.prov-req ifUnchecked.prov-req ifChanged.prov-req', function () {
        $.each(fields, function (_, fieldName) {
          updateFieldVisibility(fieldName);
        });
      });
  });
  $.each(inputTriggers, function (trigger, fields) {
    getField(trigger).off('input.prov-req change.prov-req')
      .on('input.prov-req change.prov-req', function () {
        $.each(fields, function (_, fieldName) {
          updateFieldVisibility(fieldName);
        });
      });
  });

  // External checkbox -> field required listeners
  $.each(externalRequired, function (fieldName, $checkbox) {
    $checkbox.off('ifChecked.prov-req ifUnchecked.prov-req')
      .on('ifChecked.prov-req ifUnchecked.prov-req', function () {
        updateExternalRequired(fieldName);
      });
    getField(fieldName).off('input.prov-ext').on('input.prov-ext', function () {
      var required = $checkbox.is(':checked');
      $(this).attr('data-parsley-excluded', !required && !$(this).val());
    });
  });

  // Set initial state
  $.each(mutualRequired, function (_, pair) {
    updateMutualRequired(pair);
  });
  $.each(fieldsWithRegex, function (_, fieldName) {
    updateRegexVisibility(fieldName);
  });
  $.each(fieldVisibility, function (fieldName) {
    updateFieldVisibility(fieldName);
  });
  $.each(externalRequired, function (fieldName) {
    updateExternalRequired(fieldName);
  });
}

function samlFieldConfig () {
  return {
    fieldsWithRegex: [
      'field_username', 'field_name', 'field_email', 'field_photo',
      'field_category', 'field_group', 'field_role'
    ],
    fieldVisibility: {
      auto_register_roles: { checkbox: 'auto_register', optional: true },
      field_category:      { checkbox: 'guess_category' },
      group_default:       { checkbox: 'auto_register', optional: true },
      field_group:         { checkbox: 'auto_register', empty: 'group_default' },
      role_default:        { checkbox: 'auto_register', optional: true },
      field_role:          { checkbox: 'auto_register', empty: 'role_default' },
      role_admin_ids:      { checkbox: 'auto_register', optional: true },
      role_manager_ids:    { checkbox: 'auto_register', optional: true },
      role_advanced_ids:   { checkbox: 'auto_register', optional: true },
      role_user_ids:       { checkbox: 'auto_register', optional: true }
    },
    mutualRequired: [
      ['metadata_url', 'metadata_file']
    ]
  };
}


/**
 * Populates form fields inside a container with values from a data object.
 * Supports nested objects (via recursion), checkboxes (via iCheck), multi-value
 * selects (arrays), and standard inputs. Field names use bracket notation
 * to match nested keys (e.g. "ldap_config[host]").
 *
 * @param {jQuery} $container - The container element holding the form fields.
 * @param {Object} data - Key-value pairs to fill into the form.
 * @param {string} [prefix] - Optional bracket-notation prefix for nested keys
 *                             (e.g. "ldap_config"). Used internally during recursion.
 */
function fillFormData ($container, data, prefix) {
  $.each(data, function (key, value) {
    var fullKey = prefix ? prefix + '[' + key + ']' : key;
    // Recurse into nested objects to flatten them into bracket-notation keys
    if ($.isPlainObject(value)) {
      fillFormData($container, value, fullKey);
      return;
    }
    var $field = $container.find("[name='" + fullKey + "']");
    if (!$field.length) return;
    if ($field.is(':checkbox')) {
      $field.iCheck(value ? 'check' : 'uncheck').iCheck('update').trigger('ifChanged');
    } else if ($.isArray(value)) {
      if ($field.is('select[multiple]') && $field.find('option').length) {
        // Static-option multiselects: select matching options
        $field.val(value).trigger('change');
      } else {
        // Dynamic multiselects: replace options with the provided values
        $field.empty();
        $.each(value, function (_, item) {
          $field.append(new Option(item, item, true, true));
        });
        $field.trigger('change');
      }
    } else {
      $field.val(value).trigger('change');
    }
  });
  // Validate form only on the top-level call, after all fields are populated
  if (!prefix) {
    var $form = $container.closest('form');
    if (!$form.length) $form = $container.filter('form');
    if ($form.length) $form.parsley().validate();
  }
}

/**
 * Resets all form fields inside a container to their default state.
 * Checkboxes are unchecked via iCheck, multi-selects are emptied, single
 * selects reset to the first option, and other inputs are restored to their
 * HTML default value. Parsley validation state is also reset.
 *
 * @param {jQuery} $container - The container element holding the form fields.
 */
function resetFormData ($container) {
  $container.find(':checkbox').each(function () {
    $(this).iCheck('uncheck').iCheck('update').trigger('ifChanged');
  });
  $container.find('select[multiple]').each(function () {
    var $select = $(this);
    if ($select.find('option').length) {
      // Static-option multiselects: restore default selected state
      $select.find('option').each(function () {
        this.selected = this.defaultSelected;
      });
      $select.trigger('change');
    } else {
      $select.empty().trigger('change');
    }
  });
  $container.find('select:not([multiple])').each(function () {
    $(this).prop('selectedIndex', 0).trigger('change');
  });
  $container.find(':input:not(:checkbox):not(select):not(button)').each(function () {
    $(this).val(this.defaultValue).trigger('change');
  });
  var $form = $container.closest('form');
  if (!$form.length) $form = $container.filter('form');
  if ($form.length) $form.parsley().reset();
}

/**
 * Collects form data from all inputs inside a container and returns it as a
 * nested object. Inputs excluded from Parsley validation or without a name
 * attribute are skipped. Field names in bracket notation (e.g. "ldap_config[host]")
 * are parsed into nested object keys (e.g. { ldap_config: { host: "..." } }).
 *
 * Supported input types:
 *  - Checkboxes: collected as booleans.
 *  - Number inputs: parsed as integers.
 *  - All others: collected via jQuery .val().
 *
 * @note Since jQuery 3.0, .val() returns arrays for multi-selects.
 *
 * @param {jQuery} $container - The container element holding the form fields.
 * @returns {Object} A nested object representing the collected form data.
 */
function collectFormData ($container) {
  var data = {};
  $container.find(':input').each(function () {
    var name = $(this).attr("name");
    if (!name) return;
    // Skip inputs excluded from validation (hidden form sections)
    if ($(this).attr('data-parsley-excluded') === 'true') return;
    // Parse bracket-notation name into an array of keys
    // e.g. "ldap_config[host]" → ["ldap_config", "host"]
    var keys = name.replace(/\]/g, '').split('[');
    var value;
    if ($(this).is(":checkbox")) {
      value = $(this).is(":checked");
    } else if ($(this).attr("type") === "number") {
      value = parseInt($(this).val(), 10);
    } else {
      value = $(this).val();
    }
    // Build nested object structure by traversing intermediate keys
    // e.g. keys ["ldap_config", "host"] → data.ldap_config.host = value
    var target = data;
    for (var i = 0; i < keys.length - 1; i++) {
      if (!(keys[i] in target)) target[keys[i]] = {};
      target = target[keys[i]];
    }
    target[keys[keys.length - 1]] = value;
  });
  return data;
}

function showAndHideByCheckbox (checkboxSelector, divSelector) {
  toggleFormSection(divSelector, false);
  checkboxSelector.on('ifChanged', function () {
    var isExcluded = $(this).attr('data-parsley-excluded') === 'true';
    toggleFormSection(divSelector, $(this).is(':checked') && !isExcluded);
  })
}

function populateDeleteModalTable(values, table, columns = null) {
    var tbody = table.find('tbody');
    tbody.empty();
    if (values.length > 0) {
        if ($.fn.DataTable.isDataTable(table)) {
            table.DataTable().clear().destroy();
        }
        let initOptions = {
            "data": values,
            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
            },
            "searching": false,
            "ordering": false,
            "paging": values.length > 5,
            "lengthChange": false,
            "pageLength": 5,
            'autoWidth': false,
            "info": false,
        }
        if (!columns) {
            initOptions["columns"] = [
                { 'data': 'name' },
                {
                    'data': 'user_name',
                    'render': function (data, type, row) {
                        if (row.user_name) {
                            return `${row.user_name} [${row.username}]`;
                        } else if (row.username) {
                            return row.username;
                        }
                        return '';
                    }
                }
            ]
            table.DataTable(initOptions)
        } else {
            initOptions["columns"] = columns.map(function (column) {
                return {
                    'data': column,
                    'render': function (data, type, row) {
                        if (column === "persistent") {
                            return data == false ? "No" : "Yes";
                        } else if (column === "duplicate_parent_template") {
                            return data ? "Yes" : "No";
                        }
                        return data !== undefined ? data : '';
                    }
                };
            });
            table.DataTable(initOptions);
        }
        table.DataTable().columns.adjust()
    } else {
        tbody.append(`<tr class="active"><td colspan="2" style="text-align:center;">No items</td></tr>`);
    }
}

function showLoadingData(table) {
    $(table + ' tbody').empty()
    $(table + ' tbody').append(`
        <tr class="active" id="loading-warn">
            <td colspan="3" style="text-align:center;">
                <i class="fa fa-spinner fa-pulse fa-fw">
                </i> Loading data...
            </td>
        </tr>
    `);
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

function showExportButtons (table, buttonsRowClass) {
    new $.fn.dataTable.Buttons( table, {
        buttons: [
            'csv', 'excel', 'print'
        ]
    } ).container()
    .appendTo( $('.' + buttonsRowClass) );
}    

function showLoading(loading) {
    if (loading) {
        $('#modal-loading').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
    } else {
        $('#modal-loading').modal('hide');
    }
    return false;
}

/**
 * Format bytes into human-readable size with proper units
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size (e.g., "1.67 MB", "50.00 GB")
 */
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const gb = bytes / 1024 / 1024 / 1024;
  if (gb >= 1) {
    return gb.toFixed(2) + ' GB';
  }
  const mb = bytes / 1024 / 1024;
  if (mb >= 1) {
    return mb.toFixed(2) + ' MB';
  }
  const kb = bytes / 1024;
  if (kb >= 1) {
    return kb.toFixed(2) + ' KB';
  }
  return bytes + ' B';
}
