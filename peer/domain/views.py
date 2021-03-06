# Copyright 2011 Terena. All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:

#    1. Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.

#    2. Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#        and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY TERENA ``AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL TERENA OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of Terena.

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.utils.translation import ugettext as _

from peer.domain.forms import DomainForm
from peer.domain.models import Domain, DomainTeamMembership
from peer.entity.models import Entity
from peer.domain.validation import http_validate_ownership
from peer.domain.validation import dns_validate_ownership


@login_required
def domain_add(request):
    if request.method == 'POST':
        form = DomainForm(request.POST)
        if form.is_valid():
            messages.success(request, _(u'Domain created'))
            instance = form.save(commit=False)
            instance.owner = request.user
            instance.save()
            return HttpResponseRedirect(
                reverse('domain_verify',
                        kwargs={'domain_id': instance.id}))
        else:
            messages.error(request, _('Please correct the errors'
                                      ' indicated below'))

    else:
        form = DomainForm()

    return render_to_response('domain/add.html', {
            'form': form,
            }, context_instance=RequestContext(request))


@login_required
def domain_verify(request, domain_id):
    domain = get_object_or_404(Domain, id=domain_id, owner=request.user)
    valid = False
    if request.method == 'POST':
        if u'http' in request.POST:
            if (http_validate_ownership(domain.validation_url) or
                http_validate_ownership(domain.validation_url_with_www_prefix)):
                valid = True
        elif u'dns' in request.POST:
            if dns_validate_ownership(domain.name, domain.validation_key):
                valid = True
        else:
            raise ValueError("No validation mode in POST request, "
                             "it must have either 'http' or 'dns'.")

        if valid:
            domain.validated = True
            domain.save()
            messages.success(
                request, _(u'The domain ownership was successfully verified'))
            return HttpResponseRedirect(reverse('account_profile'))
        else:
            messages.error(
                request, _(u'Error while checking domain ownership'))

    return render_to_response('domain/verify.html', {
            'domain': domain,
            }, context_instance=RequestContext(request))


@login_required
def domain_remove(request, domain_id):
    domain = get_object_or_404(Domain, id=domain_id)
    if domain.owner != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        domain.delete()
        messages.success(request, _('Domain removed succesfully'))
        return HttpResponseRedirect(reverse('account_profile'))

    return render_to_response('domain/remove.html', {
            'domain': domain,
            'entities': domain.entity_set.all(),
            }, context_instance=RequestContext(request))


@login_required
def force_domain_ownership(request, domain_id):
    domain = get_object_or_404(Domain, id=domain_id)
    if not request.user.is_superuser or domain.owner != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        domain.validated = True
        domain.save()
        messages.success(request, _('Domain ownership set by force as verified'))
        return HttpResponseRedirect(reverse('manage_domain', args=[domain.id]))

    return render_to_response('domain/force_ownership.html', {
            'domain': domain,
            }, context_instance=RequestContext(request))


@login_required
def manage_domain(request, domain_id):
    domain = get_object_or_404(Domain, id=domain_id)
    if domain.owner != request.user:
        raise PermissionDenied
    
    if request.user.is_superuser and domain.validated:
        return manage_domain_team(request, domain_id)
    
    return domain_verify(request, domain_id)


# DOMAIN SHARING

def can_share_domain(user, domain):
    return user.is_superuser and domain.validated and user == domain.owner

@login_required
def manage_domain_team(request, domain_id):
    domain = get_object_or_404(Domain, id=domain_id)
    if not can_share_domain(request.user, domain):
        raise PermissionDenied

    return render_to_response('domain/sharing.html', {
            'domain': domain,
            }, context_instance=RequestContext(request))


@login_required
def list_delegates(request, domain_id):
    domain = get_object_or_404(Domain, id=domain_id)
    if not can_share_domain(request.user, domain):
        raise PermissionDenied

    return render_to_response('domain/list_delegates.html', {
            'domain': domain,
            'delegates': domain.team.all(),
            }, context_instance=RequestContext(request))


@login_required
def add_delegate(request, domain_id, username):
    domain = get_object_or_404(Domain, id=domain_id)
    if not can_share_domain(request.user, domain):
        raise PermissionDenied

    user = User.objects.get(username=username)
    if user:
        if user in domain.team.all():
            return 'delegate'
        else:
            membership = DomainTeamMembership(domain=domain, member=user)
            membership.save()

    return list_delegates(request, domain_id)


@login_required
def remove_delegate(request, domain_id, username):
    domain = get_object_or_404(Domain, id=domain_id)
    if not can_share_domain(request.user, domain):
        raise PermissionDenied

    user = User.objects.get(username=username)
    if user:
        if user not in domain.team.all():
            return 'notdelegate'
        else:
            entities = Entity.objects.filter(owner=user)
            for entity in entities:
                if entity.domain == domain:
                    return 'hasentities'

            membership = DomainTeamMembership.objects.get(domain=domain,
                                                          member=user)
            membership.delete()

    return list_delegates(request, domain_id)
