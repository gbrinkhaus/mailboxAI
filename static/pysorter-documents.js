// globals

// When doc ready **
$(document).ready(function() {
    // ! local storage can only store strings
    restoreAccordionPanel();
    restoreTabStates();
    //console.log( "documents page ready!" );

    $('[data-toggle="tooltip"]').tooltip();

    // All of this not needed anymore due to template calling instead of reloading doc modal
    // fileModalOpen = localStorage.getItem("fileModalOpen");
    // if(fileModalOpen == "true") {
    //     //console.log( "opening modal!" );
    //     $('#fileModal').modal('show');
    //     ; }
    // else {
    //     //console.log( "closing modal!" );
    //     $('#fileModal').modal('hide');
    //     }
});


$("#fileModal").on("hidden.bs.modal", function () {
    console.log( "closing modal!" );
    location.reload();
// not needed anymore due to template calling instead of reloading doc modal
// localStorage.setItem("fileModalOpen", "false");
});


// Delete tag from a file *************************************
function deleteTag(fileid, label, tag, htmlelement) {
    $.ajax({
        url: '/deleteTagToFile',
        type: 'POST',
        contentType: "application/json",
        dataType: 'json',
        data: JSON.stringify( {'id': fileid, 'label': label, 'tag': tag} ),
        success: function(response) { 
        }, 
        error: function (error) { console.log(error); }
        });

    jQuery(htmlelement.parentNode).remove();
};


// Add tag to a file *************************************
function addTag(fileid, label, tag) {
    
    $.ajax({
        url: '/addTagToFile',
        type: 'POST',
        contentType: "application/json",
        dataType: 'json',
        data: JSON.stringify( {'id': fileid, 'label': label, 'tag': tag} ),
        success: function(response) { 
            console.log("tag to file sucess!");
            // location.reload();
         }, 
        error: function (error) { console.log(error); }
        });

    insert = `<div class="btn-group btn-group-sm ner-group" role="group">
        <button class='btn btn-primary' type='button' placeholder='${tag}' role="button">${tag}</button>
        <button type="button" onclick="javascript:deleteTag(${fileid},'${label}','${tag}', this);" class="btn fas fa-regular btn-ner-delete">x</button>
        </div>`;
    console.log(insert);
    $('#currenttags').append(insert);
};


// Add tag to a file *************************************
function addFileToDB(fileobj) {

    console.log(fileobj);

    $.ajax({
        url: '/addFileToDB',
        type: 'POST',
        contentType: "application/json",
        dataType: 'json',
        data: JSON.stringify( fileobj ),
        success: function(response) { 
            console.log("add file to db sucess!");
            location.reload();
         }, 
        error: function (error) { console.log(error); }
        });
};


// FILTER funcs **************************************************************************

// Enter a filter value *************************************
function selectFilter(id, text, numlevels) {
    document.getElementById(id).value = text.trim();
    filtersToApp(numlevels);
};


// To remove a tag from a specific tag form field *************************************
function removeFilter(label, text) {
    dict = getFilterDict();
    console.log(label, text, dict);

    if(label == "FILE" || label == "DATE") {
        dict[label] = "";
        }
    else {
        array = dict[label];
        if(array) {
            index = array.indexOf(text);
            if(index > -1) {
                array.splice(index, 1);
                dict[label] = array;
            }
        }
    }

    //console.log(JSON.stringify(dict));
    document.getElementById('Filter-Hints').value = JSON.stringify(dict);

    filtersToApp();
};


// To add a tag to a filter field *************************************
function addFilter(label, text) {
    dict = getFilterDict();

    if(!dict[label])
        dict[label] = [];

    if(label == "FILE" || label == "DATE")
        dict[label] = text;
    else {
        if(text && dict[label].indexOf(text) == -1)
            dict[label].push(text);
        }

    console.log(JSON.stringify(dict));
    document.getElementById('Filter-Hints').value = JSON.stringify(dict);

    filtersToApp();
};


// To add a tag to a filter field *************************************
function getFilterDict() {
    dict = {};

    var filters = document.getElementById('Filter-Hints').value.replace("'", '"');
    //console.log(filters);
    if(filters)
        dict = JSON.parse(filters);

    return dict;
};



// Clear all filters, then hand over to flask app *************************************
function clearFilters() {
    document.getElementById('Filter-Hints').value = "";
    filtersToApp();
};


// Hand over the values of all form fields to flask app *************************************
function filtersToApp() {
    var dict = {};
    var filters = document.getElementById('Filter-Hints').value;
    if(filters)
        dict = JSON.parse(filters);

    //console.log(JSON.stringify(dict));

    $.ajax({
        url: '/setFilter',
        type: 'POST',
        contentType: "application/json",
        dataType: 'json',
        data: JSON.stringify(dict),
        success: function(response) { 
            location.reload();
            toggleAccordions("show");
        }, 
        error: function (error) { console.log(error); }
        });
};


// Hand over the values of all form fields to flask app *************************************
function checkTags(fileobj) {
    $.ajax({
        url: '/checkTags',
        type: 'POST',
        contentType: "application/json",
        dataType: 'json',
        data: JSON.stringify(fileobj),
        success: function(response) { 
            location.reload();
        }, 
        error: function (error) { console.log(error); }
        });
};


// MODAL funcs **************************************************************************
// In order to add tags to the filter card box *************************************
function openactionFilterModal() {
    $("#actionFilterModal").modal('show');
}
// In order to add tags to the filter card box *************************************
function opentagFilterModal() {
    $("#tagFilterModal").modal('show');
}

// In order to open + store the state of the modal - the real opening will happen on docready func *************************************
function openDocModal(fullpath) {

    html = fetch('/selectDocument', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(fullpath) })
    .then(data => {
        return data.text();
    })
    .then(html => {
        //console.log(html);
        $('#fileModalContents').html(html);
        $('#fileModal').modal('show');

    });
};


// ACCORDION funcs **************************************************************************

// Toggle all accordions *************************************
$('.acco-toggle-all').click(function() {
    action = 'show';

    // if not initialised yet, hide all
    if ($(this).data("lastState") === null || $(this).data("lastState") === 0) 
        action = 'hide';

    toggleAccordions(action);
});

function toggleAccordions(action) {
    tbutton = $('.acco-toggle-all');

    if(action == 'hide') {
        tbutton.data("lastState",1);
        tbutton.text('\uf103');
    }
    else {
        tbutton.data("lastState",0);
        tbutton.text('\uf102');
    }

    $('#doclist .accordion-collapse').collapse(action);
}

// Save + restore state of all ACCS *************************************
$('#doclist').on('shown.bs.collapse', function (e) {
    saveAccordionState(e.target.id); 
    // to make sure a tab is always selected
    enableOneTab(e.target.id); 
});

$('#doclist').on('hidden.bs.collapse', function (e) {
    saveAccordionState(e.target.id); });
   
function saveAccordionState(accordionId) {
    allOpenCollapses = $('#doclist .accordion-collapse.show');
    // extract the ids only for cleaner storage usage
    openC = [];
    for(const element of allOpenCollapses) {
        openC.push("#" + element.id) }
    localStorage.setItem('accstate', JSON.stringify(openC));
}
    
function restoreAccordionPanel() {
    var activeItems = localStorage.getItem('accstate');
    if (activeItems) {
        accs = JSON.parse(activeItems); 
        for (const element of accs) {
            // element is the collapse item itself, button is the corresponding button
            accbuton = $('[href="' + element +'"]');
            accbuton.removeClass('collapsed');
            $(element).addClass('show');
            //$(element).collapse('show');
        }
    }
}


// Save + restore state of all TABS *************************************
$('#doclist').on('shown.bs.tab', function (e) {
    saveTabState(e.target.id); });

$('#doclist').on('hidden.bs.tab', function (e) {
    saveTabState(e.target.id); });

// to make sure one tab is always selected
function enableOneTab(parentid) {
    tablist = $("#" + parentid + " .nav-link");
    console.log(parentid, tablist);

    if(tablist){
        found = false;
        for(const link in tablist)
            if(jQuery(link).hasClass('active'))
                found = true;
        if(!found)
            showTab(tablist[0].id, true);
    }
}

// to enable or disable a specific tab 
function showTab(navid, turnon) {
    //pnumber = parentid.replace(/^\D+/g, '');
    tabcontent = $( $(navid).attr('data-bs-target') );
    //console.log(navid);

    if(turnon) {
        $(navid).addClass('active');
        tabcontent.addClass('active');
        tabcontent.addClass('show');
    }
    else {
        $(navid).removeClass('active');
        tabcontent.removeClass('active');
        tabcontent.removeClass('show'); 
    }
}

function saveTabState(tabID) {
    allOpenTs = $('#doclist .nav-link.active');
    openT = []; // doing this for cleaner storage usage
    for(const element of allOpenTs) {
        openT.push("#" + element.id)
        }
    localStorage.setItem('tabstate', JSON.stringify(openT));
}
    
function restoreTabStates() {
    var activeItems = localStorage.getItem('tabstate');
    var storedTabs = [];
    if (activeItems) 
        storedTabs = JSON.parse(activeItems); 

    allTabs = $('#doclist .nav-tabs');
    for(const tab of allTabs) {
        allLinks = $('#' + tab.id +' .nav-link');
        found = false;
        for(const link of allLinks) {
            if(storedTabs.includes('#'+link.id) && !found) {
                showTab(link, true); 
                found = true;
                }
            else
                showTab(link, false); 
            }

            if(!found)
                showTab(allLinks[0], true); 
        }
    }


