"""Shared Admin/Capstone Professor roster management; never public roster data."""
from functools import wraps
from io import BytesIO
import csv
import secrets
from io import StringIO
from flask import abort, current_app, flash, redirect, render_template, request, session, send_file, url_for
from . import admin
from app.db import roster,roster_stage
from app.services.roster_import import HEADERS

def roster_access(view):
    @wraps(view)
    def guarded(*args,**kwargs):
        try:
            roster.check_actor(session.get('user_id'))
            return view(*args,**kwargs)
        except PermissionError:
            abort(403)
    return guarded

@admin.route('/roster',methods=['GET','POST'])
@roster_access
def roster_upload():
    binding=session.setdefault('roster_import_binding',secrets.token_urlsafe(32))
    update_id=request.values.get('update_upload_id',type=int)
    update_upload=roster.read_roster(session['user_id'],upload_id=update_id)[2] if update_id is not None else None
    if update_id is not None and (not update_upload or update_upload['status']!='active'):
        abort(404)
    if request.method == 'POST':
        upload = request.files.get('master_list')
        try:
            if not upload or not upload.filename:
                raise ValueError('Choose a student master-list file.')
            if request.form.get('update_upload_id') and update_id is None:
                raise ValueError('Invalid masterlist update target.')
            token=roster_stage.create_stage(upload,request.form.get('class_name'),request.form.get('academic_year'),request.form.get('semester'),session['user_id'],binding,update_id)
        except PermissionError:
            abort(403)
        except ValueError as exc:
            flash(str(exc),'danger')
        except Exception as exc:
            current_app.logger.error('Roster import rolled back (%s)',type(exc).__name__)
            flash('Import failed; no roster changes saved. Try again later.','danger')
        else:
            return redirect(url_for('admin.roster_preview',token=token))
    history,records,_ = roster.read_roster(session['user_id'],request.args.get('search',''),registered_only=True)
    return render_template('admin/roster.html',history=history,records=records,upload=None,
                           overview=roster.roster_overview(session['user_id']),update_upload=update_upload,
                           class_masterlists=roster.read_class_masterlists(session['user_id']))

@admin.route('/roster/preview/<uuid:token>')
@roster_access
def roster_preview(token):
    try:
        preview=roster_stage.preview(str(token),session['user_id'],session.get('roster_import_binding'),request.args.get('candidate'))
    except roster_stage.StageExpired as exc:
        return render_template('admin/roster_preview.html',error=str(exc)),410
    except LookupError:
        abort(404)
    except ValueError as exc:
        return render_template('admin/roster_preview.html',error=str(exc)),400
    if preview.get('completed_upload_id'):
        return redirect(url_for('admin.roster_result',upload_id=preview['completed_upload_id']))
    rows=preview.get('rows',[])
    page=max(1,request.args.get('page',1,type=int))
    pages=max(1,(len(rows)+99)//100)
    page=min(page,pages)
    return render_template('admin/roster_preview.html',preview=preview,rows=rows[(page-1)*100:page*100],page=page,pages=pages)

@admin.route('/roster/confirm/<uuid:token>',methods=['POST'])
@roster_access
def roster_confirm(token):
    try:
        result=roster_stage.confirm(str(token),session['user_id'],session.get('roster_import_binding'),request.form.get('candidate'))
    except roster_stage.StageExpired as exc:
        return render_template('admin/roster_preview.html',error=str(exc)),410
    except LookupError:
        abort(404)
    except ValueError as exc:
        return render_template('admin/roster_preview.html',error=str(exc)),400
    except PermissionError:
        abort(403)
    except Exception as exc:
        current_app.logger.error('Roster confirmation rolled back (%s)',type(exc).__name__)
        return render_template('admin/roster_preview.html',error='Import failed; no changes saved. Retry the preview before it expires.'),503
    return redirect(url_for('admin.roster_result',upload_id=result['upload_id']))

@admin.route('/roster/uploads/<int:upload_id>')
@roster_access
def roster_result(upload_id):
    history,records,upload = roster.read_roster(session['user_id'],request.args.get('search',''),upload_id,registered_only=True)
    if not upload:
        abort(404)
    return render_template('admin/roster.html',history=history,records=records,upload=upload,
                           overview=roster.roster_overview(session['user_id']),
                           class_masterlists=roster.read_class_masterlists(session['user_id']))

@admin.route('/roster/template/<file_type>')
@roster_access
def roster_template(file_type):
    if file_type == 'csv':
        text = StringIO()
        csv.writer(text).writerow(HEADERS)
        content = text.getvalue().encode('utf-8-sig')
        mimetype = 'text/csv'
    elif file_type == 'xlsx':
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.title = 'Students'
        sheet.append(HEADERS)
        sheet.append(['001234','Example','','Student','student@example.edu'])
        sheet['A2'].number_format = '@'
        output = BytesIO()
        book.save(output)
        content = output.getvalue()
        book.close()
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        abort(404)
    return send_file(BytesIO(content),mimetype=mimetype,as_attachment=True,download_name='student-master-list.'+file_type,max_age=0)

@admin.route('/roster/records/<int:roster_id>')
@roster_access
def roster_record(roster_id):
    record = roster.get_record(session['user_id'],roster_id)
    if not record:
        abort(404)
    return render_template('admin/roster_record.html',record=record)
