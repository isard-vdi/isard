/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

function filterTemplate(obj) {
	kind=obj.value;
    var dropdownList = document.getElementById("template");
	$.ajax({
		type: "GET",
		url:"/desktops/filterTemplate/" + kind,
		success: function(templates)
		{
		  var categories= Object.keys(templates);
		  var total=0;
		  var content='';
		  for (var i=0; i<categories.length; i++) {
			  	if(categories[i]!='null'){
					content=content+'<optgroup label="CATEGORY: '+categories[i]+'">';
				}
				for (var j=0; j<templates[categories[i]].length; j++) {
					total+=1;
					content=content+'<option value="'+templates[categories[i]][j]['id']+'" >'+templates[categories[i]][j]['name']+'</option>';
				}
			}
		  content='<optgroup label="Found '+total+' templates, choose one:">'+content;
		  dropdownList.innerHTML=content;
		  $('#labelfilters').text("");
		  if(kind=='public_template'){
		  	templateFiltersFill(kind);
	  	  }else{
			//~ if(kind=='public_template'){visible='visible';}else{visible='hidden';}
		  }
		  //~ $('.form-select-2').css("display", "block");
		}
	});

}

function templateUpdate(element) {
	var type = element.options[element.selectedIndex].value;
	setHardwareDomainDefaults('#modalAddDesktop',type);
}

function templateFiltersFill(kind){
		var dropdownUsers = document.getElementById("templateFilterUser");
		var dropdownCategory = document.getElementById("templateFilterCategory");
		var dropdownGroup = document.getElementById("templateFilterGroup");
		$.ajax({
			type: "GET",
			url:"/desktops/getDistinc/"+"user"+"/"+kind,
			success: function(dictOptions)
			{
			  var options= Object.keys(dictOptions);
			  var content='<option value="-1">Select:</option>';
			  for (var i=0; i<options.length; i++) {
					content=content+'<option value="'+options[i]+'" >'+options[i]+'</option>';
				}
			  dropdownUsers.innerHTML=content;
			}
		});
		$.ajax({
			type: "GET",
			url:"/desktops/getDistinc/"+"category"+"/"+kind,
			success: function(dictOptions)
			{
			  var options= Object.keys(dictOptions);
			  var content='<option value="-1">Select:</option>';
			  for (var i=0; i<options.length; i++) {
					content=content+'<option value="'+options[i]+'" >'+options[i]+'</option>';
				}
			  dropdownCategory.innerHTML=content;
			}
		});
		$.ajax({
			type: "GET",
			url:"/desktops/getDistinc/"+"group"+"/"+kind,
			success: function(dictOptions)
			{
			  var options= Object.keys(dictOptions);
			  var content='<option value="-1">Select:</option>';
			  for (var i=0; i<options.length; i++) {
					content=content+'<option value="'+options[i]+'" >'+options[i]+'</option>';
				}
			  dropdownGroup.innerHTML=content;
			}
		});		
}

function filterTemplateBy(field,element) {
	var value = element.options[element.selectedIndex].value;
	var dropdownList = document.getElementById("template");
	$.ajax({
		type: "GET",
		url:"/desktops/filterTemplate/public_template/"+field+"/" + value,
		success: function(templates)
		{
		  var categories= Object.keys(templates);
		  var total=0;
		  var content='';
		  for (var i=0; i<categories.length; i++) {
			  	if(categories[i]!='null'){
					content=content+'<optgroup label="CATEGORY: '+categories[i]+'">';
				}
				for (var j=0; j<templates[categories[i]].length; j++) {
					total+=1;
					content=content+'<option value="'+templates[categories[i]][j]['id']+'" >'+templates[categories[i]][j]['name']+'</option>';
				}
			}
		  content='<optgroup label="Found '+total+' templates, choose one:">'+content;
		  dropdownList.innerHTML=content;
		  $('#labelfilters').text("Filtered by [ "+field+" = "+value+" ]");
          $('#templateFilterUser').val(-1);
          $('#templateFilterGroup').val(-1);
          $('#templateFilterCategory').val(-1);
		}				
	});
}
