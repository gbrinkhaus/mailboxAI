// globals

// When doc ready, check whether a file has been OCRed - if, so, we need to display form elements **
$(document).ready(function() {
    //console.log( "ready!" );
    //alert(filename);

    var hide = true;
    var url = window.location.pathname;
    var filename = url.substring(url.lastIndexOf('/')+1);

    // number of levels is not dynamic anymore
    maxlevels = 3;

    // if url string empty, it is home page
    if (filename == '') {
        if(document.getElementById('ner-tags').innerHTML.trim().length)
            hide = false;

        // hide file contents, if no file is chosen
        document.getElementById('ocrresults').hidden = hide;
        document.getElementById('folderforms').hidden = hide;

        // hide header, if file is chosen
        document.getElementById('filepicker').hidden = !hide;
        document.getElementById('header').hidden = !hide;

        // register hotkey handler, but only for Homepage
        document.addEventListener('keydown', doc_keyDown, false);

        checkSendButton();
    }

    document.getElementById('filecontents').addEventListener("mouseup", function(event) {
        var text = window.getSelection().toString().trim();
        // $("#filecontents").append("<div>" + text + "</div>");
        console.log("mouseup: " + text);

        selectionEndTimeout = setTimeout(function () {
            if(text.length > 2 && text.length < 200) {
                // $('#tagModal').moveTo( window.getSelection().getRangeAt(0).getBoundingClientRect() );
                rect = window.getSelection().getRangeAt(0).getBoundingClientRect();
                openNewTagWindow(text, "MISC", text, rect.left, rect.top);
                // console.log("mouseup: " + text);
                }
        }, 200);

    }, false);
    
/*    document.addEventListener("selectionchange", function(event) {
        var text = window.getSelection().toString();
        $(".filecontents").append("<div>" + text + "</div>");
        // console.log("selchange: " + text);
    }, false); */

});


// check whether OCR document is active
function OCRisActive() {
    return ! document.getElementById('ocrresults').hidden;
}


// define a handler
function doc_keyDown(e) {

    if (OCRisActive()) {
        if (e.altKey) {
            // (1) key is 49
            oneKey = 49;
            theKey = e.keyCode - oneKey + 1;
            success = false;

            if (theKey >= 1 && theKey <= maxlevels) {
                // console.log(e);
                // console.log("doc_keyDown!");
                if (e.shiftKey) {
                    document.getElementById("L" + theKey.toString() + "-Groupswitcher").checked = true;
                    flashElement("#L" + theKey.toString() + "-Cards");
                    // beepsound.play();
                }
                else {
                    document.getElementById("L" + theKey.toString() + "-Textswitcher").checked = true;
                    flashElement("#L" + theKey.toString());
                }

                success = true;
            }

            if (e.keyCode == 68) { // D key
                document.getElementById("DT-Textswitcher").checked = true;
                flashElement("#DT");
                success = true;
            }

            if (e.keyCode == 70) { // F key
                document.getElementById("FN-Textswitcher").checked = true;
                flashElement("#FN");
                success = true;
            }

            if (success) {
                if (window.getSelection().toString())
                    addTag(window.getSelection().toString(), 'txt');

                e.preventDefault();
                e.stopPropagation();
            }
        }
    }
}

// open the new tag window
function setFilename() {
    // console.log("openNewTagWindow called with text: " + text);
    writeFormField("FN", $("#target-term").val().replace(/[\\\/:\*\?"<>\|]/g, "-").trim());
    }


    // setDate *************************************
function setTodaysDate(elem) {
    var curdt = new Date();
    var mo = curdt.getMonth() + 1;

    // padding JS style
    document.getElementById(elem).value =
        curdt.getDate().toString().padStart(2, '0') + "." +
        mo.toString().padStart(2, '0') + "." + curdt.getFullYear();

    checkSendButton();
};


// open the new tag window
function openNewTagWindow(text, type, hint, left, top) {
    text = text.trim()
    type = type.trim()
    if (typeof hint == 'undefined')
        hint = text;
    else 
        hint = hint.trim()
    // console.log("openNewTagWindow called with text: ", text, type, hint);

    modal = $('#tagModal');
    modaldlg = modal.children(".modal-dialog");

    $("#target-term").attr("value", text);
    $("#target-term").prop("value", text);
    $("#target-type").html(type);
    $("#newhinttext").html(hint);
    $('#error-container').prop('hidden', true);
    $('#notice-container').prop('hidden', true);

    /* so much work went into the positioning, now discarding it
    if(left != null && top != null) {
        modaldlg.css('left', ((window.innerWidth * -.5) + left + 250) + "px");
        modaldlg.css('top', top + "px");
        } */
        
    modal.modal('show');
    }


// open the new tag window
function openAddFolderWindow() {
    modal = $('#addFolderModal');
    modal.modal('show');

    }


// To do both the writing into the HTML and the DB *************************************
function addNewAction(text, action) {
    addAction(text, action);
    writeTag(text, "ACTION", action, false);
}


// To write a tag into the HTML of tag form field *************************************
function addAction(text, action) {
    text = text.trim()
    type = "ACTION"
    if (typeof action == 'undefined')
        action = "";

    var tag = $("#ACTION-Cards");
    entries = $(tag).find('button.btn.btn-primary').toArray();

    found = false;
    for (i = 0; i < entries.length; i++) {
        if (entries[i].innerText == text)
            found = true;
        }

    activeState = "";
    /* if(chldren.length == 0)
        activeState = " active"; */
    buttonid = type + text.replace(" ", "");
    
    if (!found) {
        // Important to add button with type "button" to prevent form submit
        insert = `<button class='btn btn-primary ${activeState}' type='button' placeholder='${action}' role="button"
            onclick="window.open('https://${action}','_blank')" target="_blank" id="${buttonid}"> 
            ${text} </button>`;

        // console.log(insert);

        tag.append('<div class="btn-group btn-group-sm confirmed-ners" role="group">' +
            insert + '<button type="button" onclick="javascript:removeAction(this);" class="btn fas fa-regular btn-ner-delete">x</button></div>');
        }

    checkSendButton();
        // targetInput.value += type + "||" + text + "||";
};

// To write a tag into a specific tag form field *************************************
function selectFolder(text, type, hint, level) {
    console.log("selFolder text, type, hint, level:\n", text, type, hint, level);
    level = parseInt(level);

    for(i = 1; i <= 3; i++) {

        if(i == level)
            $('#FModalText'+i.toString()).prop("value", text);
        else if(i == level + 1) {
            $('#FModalText'+i.toString()).prop("value", "");
            $('#FModalText'+i.toString()).attr('placeholder', "Folder " + i.toString());
        }
        else if(i > level) {
            $('#FModalText'+i.toString()).prop("value", "");
            $('#FModalText'+i.toString()).attr('placeholder', "");
        }

        if(i == level + 1) {
            $('#FModalList'+i.toString()+" li").each(function( e ) {
                // console.log($(this).attr('parentfolder')) ;
                if( $(this).attr('parentfolder') == text )
                    $(this).show()
                else
                    $(this).hide()
                // $(this).prop("disabled", $(this).attr('parentfolder') != text);
            });         
            }

        disable = true;
        if(i <= level + 1)
            disable = false;
        // document.getElementById('FModalDropdwn'+i.toString()).disabled = disable;
        $('#FModalDropdwn'+i.toString()).prop("disabled", disable);
    }
    
    addTag(text, type, hint, level);
}

// To write a tag into a specific tag form field *************************************
function addTag(text, type, hint, level = "-") {

    text = text.trim();
    type = type.trim();
    if (typeof hint == 'undefined')
        hint = text;
    // this is a little hack, to prevent errors when somebody should actually add a tag with my internal delimiter
    hint = hint.trim().replace("||", "XX");
    activetag = (level == "-") ? "" : "active";

    var tag = $("#" + type + "-Cards");
    entries = $(tag).find('button.btn.btn-primary').toArray();

    found = false;
    for (i = 0; i < entries.length; i++) {
        if (entries[i].innerText == text)
            found = true;
        }

    buttonid = type + text.replace(" ", "");

    if (!found) {
        tag.append('<div class="btn-group btn-group-sm confirmed-ners" role="group">' +
            `<button type="button" class="btn btn-tagpath ${activetag}" role="button" onclick="javascript:changePathOrder(this, true);">${level}</button>` +
            `<button class='btn btn-primary ${activetag}' type='button' placeholder='${hint}' role="button"
            ondblclick='javascript:openNewTagWindow("${text}", "${type}", "${hint}");'
            onclick='javascript:changePathOrder(this, false);' id="${buttonid}"> 
            ${text} </button>`
            + '<button type="button" onclick="javascript:removeTag(this);" class="btn fas fa-regular btn-ner-delete">x</button></div>');
        }

    checkSendButton();
        // targetInput.value += type + "||" + text + "||";
};


// To remove a tag from a specific tag form field *************************************
// changeorder says whether to just turn the button on/off or actually switch positions
function changePathOrder(btngroupclicked, changeorder) {
    buttonarray = $('form .ner-group .confirmed-ners');
    clickedbutton = getTagButton(btngroupclicked);
    wasActive = clickedbutton[1].classList.contains("active");
    clickedposition = parseInt(clickedbutton[0].innerHTML)
    patharray = [];

    //console.log("pressed", clickedbutton[1].id, "was active", wasActive, "changeorder", changeorder);

    // iterate thrg all confimed tag buttons (right side)
    for (i=0; i < buttonarray.length; i++) {
        // add only active buttons that are not the initiator
        button = getTagButton(buttonarray[i]);
        if(button[1].classList.contains("active") && button[1].id != clickedbutton[1].id) {
            //console.log("storing active button", button[1].innerHTML);
            patharray.push(button);
        }
    }

    patharray.sort(function(a, b){ 
        return parseInt(a[0].innerHTML) - parseInt(b[0].innerHTML); 
    });

    //for (i=0; i < patharray.length; i++) 
        //console.log("active button sorted", patharray[i][0].innerHTML, ": ", patharray[i][1].innerHTML);

    // if the button was not active, add to end of list
    if(!wasActive) {
        if(patharray.length >= 3) {
            patharray[patharray.length-1][0].classList.remove("active");
            patharray[patharray.length-1][1].classList.remove("active");
            patharray[patharray.length-1][0].innerHTML = "-";
            patharray.pop();
            }
        patharray.push(clickedbutton);
        }
    // if the button was active and should be moved up, do so
    else if(wasActive && changeorder) {
        if(clickedposition > 1)
            patharray.splice(clickedposition-2, 0 , clickedbutton);
        else
            patharray.splice(0, 0 , clickedbutton);
        }
    // if the button was active and should not be moved, deactivate
    else if(wasActive && !changeorder) {
        clickedbutton[0].classList.remove("active");
        clickedbutton[1].classList.remove("active");
        clickedbutton[0].innerHTML = "-";
        }

    // loop over all butoons, bringing everything in order
    for (i=0; i < patharray.length; i++) {
        //console.log("spliced array", patharray[i][1].innerHTML);
        if(i<3) {
            patharray[i][0].classList.add("active");
            patharray[i][1].classList.add("active");
            patharray[i][0].innerHTML = (i+1).toString();
        }
        else {            
            patharray[i][0].classList.remove("active");
            patharray[i][1].classList.remove("active");
            patharray[i][0].innerHTML = "-";
            }
    }

    checkSendButton();
};


// To set a tag from a specific tag form field *************************************
function checkDuplicateTags() {
    label = $('#target-type').html().trim();
    text = $('#target-term').prop('value').trim();
    storedtags = JSON.parse($('#Storedtags').text());

    if(storedtags){
        //console.log(label, text, storedtags, storedtags.length);
        found = false;
        for(i=0; i<storedtags.length; i++) {
            if(storedtags[i]['text'] == text) {
                if(storedtags[i]['label'] == label) {
                    $('#error-container').prop('hidden', true);
                    $('#notice-container').prop('hidden', false);
                }
                else {
                    $('#error-container').prop('hidden', false);
                    $('#notice-container').prop('hidden', true);
                }
                found = true;
            }
        }
        if(!found) {
            $('#error-container').prop('hidden', true);
            $('#notice-container').prop('hidden', true);
        }
    }
};


// To set a tag from a specific tag form field *************************************
function stopTag(item) {
    // console.log(item);
    clickedbutton = getTagButton(item);
    writeTag(clickedbutton[1].innerHTML, clickedbutton[0].innerHTML, "!!--STOP--!!");

    removeTag(item);
    checkSendButton();
};


// To remove a tag from a specific tag form field *************************************
function removeTag(item) {
    // console.log(item);
    clickedbutton = getTagButton(item);

    for(i=0; i< clickedbutton.length; i++)
        clickedbutton[i].classList.remove("active");

    item.parentNode.classList.remove("active");
    item.parentNode.remove();
    checkSendButton();
};


// To remove a tag from a specific tag form field *************************************
function removeAction(item) {
    // console.log(item);
    item.classList.remove("active");
    item.parentNode.classList.remove("active");
    item.parentNode.remove();
    checkSendButton();
};


// To switch through all valid versions of an Entitiy select button
function setNextEnt(buttonObject) {
    // console.log(buttonObject);

    curindex = nerEnts.indexOf(buttonObject.innerHTML);
    if(curindex != -1) {
        buttonObject.innerHTML = nerEnts[ (curindex < nerEnts.length - 1) ? curindex+1 : 0 ];
    }

    checkDuplicateTags();
};


// To write a text into a specific levels form field *************************************
function writeFormField(fld, val) {
    // console.log(fld, val); 
    document.getElementById(fld).value = val.trim();
    checkSendButton();
};


// To enable send button only when all inputs filled *************************************
function getAllLevelInputs() {
    collection = new Array();

    collection.push( ['FILE', $("#FN").val(), false] );
    collection.push( ['DATE', $("#DT").val(), false] );

    for (e=0; e < nerEnts.length; e++) {
        tag = "#" + nerEnts[e] + "-Cards";
        entries = $(tag).find('button.btn.btn-primary').toArray();

        for (i=0; i < entries.length; i++) {
            button = getTagButton(entries[i]);
            collection.push( [ nerEnts[e], button[1].innerText, parseInt(button[0].innerHTML) ] );
            }
    } 

    tag = "#ACTION-Cards";
    entries = $(tag).find('button.btn.btn-primary').toArray();

    for (i=0; i < entries.length; i++) {
        button = getTagButton(entries[i]);
        collection.push( [ "ACTION", button[1].innerText, -1 ] );
        }

    //console.log(collection);

    return collection;
};


// To enable send button only when all inputs filled *************************************
function checkSendButton() {
    var collection = getAllLevelInputs();
    var disable = false;
    var activetags = 0;

    collection.sort(function(a,b) {
        return a[2]-b[2]
    });

    for (const item of collection) { 
        if( (item[0] == 'FILE' && item[1] == '') || (item[0] == 'DATE' && item[1] == '') )
            disable = true;
        if (item[2] && item[0] != 'ACTION')
            activetags++;
        }
    if(activetags != 3)
        disable = true;

    // if there is no filename or date or not 3 entries (meaning 5 keys), disable

    // $("#FilePath").html("");
    $("#Tag-Hints").attr("value", "");

    document.getElementById('fileSendButton').disabled = disable;

    // if we have a valid path, pre-fill form fields
    if(!disable) {
        tagstring = "";
        pathstring = "/";
        htmlpathstring = "/";
        validfolders = JSON.parse($('#Validfolders').html());

        for(const id in collection) {
            key = collection[id][0];
            val = collection[id][1];
            folderid = collection[id][2];

            // console.log(key, val, folderid);

            if(key != 'FILE' && key != 'DATE' && key != 'ACTION' && folderid > 0 && folderid <= 3 ) {
                fragment = "<span>";
                if(validfolders[folderid-1].includes(val))
                    fragment = "<span class='text-success'>";
                htmlpathstring += fragment + val + "/</span>";
                pathstring += val + "/";
            }
        }
        $("#FilePath").html(htmlpathstring);
        $("#Hiddenpath").attr("value", pathstring);
        $("#Tag-Hints").attr("value", JSON.stringify(collection));
    }

};


// To call File processing in mother app *************************************
function processFile(caller) {
    var collection = getAllLevelInputs();
    for (i = 0; i < collection.length; i++) {
        if (collection[i][0] != 'FILE' && collection[i][0] != 'DATE' && collection[i][0] != 'ACTION')
            writeTag(collection[i][1], collection[i][0]);
        // console.log(collection[i]);
        // storeLevelSuggestion(collection[i].id);
    }

    caller.form.submit();
};


// testfunc *************************************
function setPdfDoc(value) {
    // console.log(value);
    // console.log(document.getElementById('modal-pic').data);
    document.getElementById('modal-pic').data = value;
    // console.log(document.getElementById('modal-pic').data);
};
