

function gen_form(div_id,data){
    $(div_id).empty()
    var html = ""
    data.forEach(function(action) {
        if(action.element == "textarea"){
            html = html + '<label >'+action.name+'</label><'+action.element+' id="' + action.id + '" class="form-control kwargs_field" style="min-width: 100%" placeholder"="'+action.placeholder+'"></'+action.element+'>'
            $(div_id).append(html)
        }
        if(action.element == "select"){
            $.ajax({
                type: action.ajax.type,
                url: action.ajax.url,
                contentType: "application/json",
                data: JSON.stringify(action.ajax.data),
                success: function(data)
                {
                    data=JSON.parse(data)
                    html = html + '<select id="'+action.id+'" name="'+action.id+'" class="form-control kwargs_field" required>"'
                    data.forEach(function(items) {
                        html = html + '<option value="'+items[action.ajax.ids]+'">'+items[action.ajax.values]+'</option>'
                    })
                    html = html + '</select>'
                }
            });
            $(div_id).append(html)
        }
        if(action.element == "select2"){
            html_select2 = '<label >'+action.name+'</label><select id="'+action.id+'" name="'+action.id+'" class="tags-select roundbox kwargs_field" style="width: 100%;"></select>'
            $(div_id).append(html_select2)
            $(div_id+" #"+action.id).select2({
                dropdownParent: $(div_id),
                minimumInputLength: 2,
                maximumSelectionSize: 1,
                showSearchBox: true,
                closeOnSelect: true,
                multiple: false,
                ajax: {
                    type: action.ajax.type,
                    url: action.ajax.url,
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return  JSON.stringify({
                            term: params.term,
                        });
                    },
                    processResults: function (data) {
                        return {
                            results: $.map(data, function (item, i) {
                                return {
                                    text: item.name,
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            });
        }
      })
    return html
}