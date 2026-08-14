package com.ruoyi.web.controller.system;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.domain.entity.SysDept;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.ISysDeptService;
import com.ruoyi.framework.web.service.SysPermissionService;
import com.ruoyi.system.service.ISysUserService;

/**
 * Read-only identity contract for Enterprise Agent Platform.
 * This adapter deliberately reuses RuoYi's existing token and data-scope rules.
 */
@RestController
@RequestMapping("/agent-iam")
public class AgentIamController extends BaseController
{
    @Value("${agent-iam.organization-id:ruoyi-default}")
    private String organizationId;

    @Autowired
    private ISysUserService userService;

    @Autowired
    private ISysDeptService deptService;

    @Autowired
    private SysPermissionService permissionService;

    @GetMapping("/me")
    public AjaxResult me()
    {
        LoginUser loginUser = SecurityUtils.getLoginUser();
        if (loginUser == null || loginUser.getUser() == null)
        {
            return error("Authentication is required");
        }
        SysUser user = loginUser.getUser();
        SysDept dept = user.getDept();
        if (dept == null && user.getDeptId() != null)
        {
            dept = deptService.selectDeptById(user.getDeptId());
        }
        Set<String> roles = permissionService.getRolePermission(user);
        AjaxResult ajax = success();
        ajax.put("userId", user.getUserId());
        ajax.put("userName", user.getUserName());
        ajax.put("nickName", user.getNickName());
        ajax.put("orgId", organizationId);
        ajax.put("dept", deptView(dept));
        ajax.put("roles", roles);
        return ajax;
    }

    @PreAuthorize("@ss.hasPermi('system:user:list')")
    @GetMapping("/users")
    public AjaxResult users(@RequestParam(defaultValue = "") String name,
            @RequestParam(defaultValue = "20") int limit)
    {
        SysUser query = new SysUser();
        query.setUserName(name);
        int safeLimit = Math.max(1, Math.min(limit, 100));
        List<Map<String, Object>> result = new ArrayList<>();
        for (SysUser user : userService.selectUserList(query))
        {
            result.add(userView(user));
            if (result.size() >= safeLimit)
            {
                break;
            }
        }
        return success(result);
    }

    @PreAuthorize("@ss.hasPermi('system:dept:list')")
    @GetMapping("/departments")
    public AjaxResult departments(@RequestParam(defaultValue = "") String name,
            @RequestParam(defaultValue = "100") int limit)
    {
        SysDept query = new SysDept();
        query.setDeptName(name);
        int safeLimit = Math.max(1, Math.min(limit, 100));
        List<Map<String, Object>> result = new ArrayList<>();
        for (SysDept dept : deptService.selectDeptList(query))
        {
            result.add(deptView(dept));
            if (result.size() >= safeLimit)
            {
                break;
            }
        }
        return success(result);
    }

    private Map<String, Object> userView(SysUser user)
    {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("userId", user.getUserId());
        view.put("userName", user.getUserName());
        view.put("nickName", user.getNickName());
        view.put("deptId", user.getDeptId());
        return view;
    }

    private Map<String, Object> deptView(SysDept dept)
    {
        if (dept == null)
        {
            return null;
        }
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("deptId", dept.getDeptId());
        view.put("deptName", dept.getDeptName());
        view.put("parentId", dept.getParentId());
        return view;
    }
}